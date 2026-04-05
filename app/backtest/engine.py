"""
engine.py — Orchestrateur principal du backtest événementiel.

Boucle stricte par barre :
  1. update_bars()          → MarketEvent dans la queue
  2. check_exits()          → ordres de sortie (stops / TP) avant les nouveaux signaux
  3. on_bar() par stratégie → SignalEvents
  4. validate_order()       → OrderEvents
  5. execute_order()        → FillEvents
  6. on_fill()              → mise à jour du portfolio
  7. on_market()            → mise à jour equity curve + log

Déterminisme garanti : pour un même CSV et une même config,
le résultat est identique à chaque exécution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from backtest.core.events import EventType, FillEvent, MarketEvent, OrderEvent, SignalEvent
from backtest.core.queue import EventQueue
from backtest.data.base import AbstractDataHandler
from backtest.execution.base import AbstractExecutionHandler
from backtest.portfolio.base import AbstractPortfolio
from backtest.reporting.metrics import compute_metrics
from backtest.risk.base import AbstractRiskManager
from backtest.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    equity_curve:    pd.Series
    trades:          list
    metrics:         dict
    run_id:          str
    started_at:      datetime
    finished_at:     datetime


class BacktestEngine:
    """
    Orchestre la boucle événementielle.
    Instanciez-le avec les composants configurés, puis appelez .run().
    """

    def __init__(
        self,
        data:        AbstractDataHandler,
        strategies:  list[BaseStrategy],
        portfolio:   AbstractPortfolio,
        risk:        AbstractRiskManager,
        execution:   AbstractExecutionHandler,
        queue:       EventQueue,
        initial_capital: float,
        log_dir:     Optional[Path] = None,
        run_id:      Optional[str] = None,
        trade_start_date: Optional[datetime] = None,
    ) -> None:
        self._data       = data
        self._strategies = strategies
        self._portfolio  = portfolio
        self._risk       = risk
        self._execution  = execution
        self._queue      = queue
        self._initial_capital = initial_capital
        self._log_dir    = Path(log_dir) if log_dir else Path("logs")
        self._run_id     = run_id or datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._trade_start = trade_start_date
        self._event_log: list[dict] = []

    # -----------------------------------------------------------------------
    # Point d'entrée principal
    # -----------------------------------------------------------------------

    def run(self) -> BacktestResult:
        started_at = datetime.utcnow()
        logger.info(f"Backtest {self._run_id} démarré.")

        while True:
            # 1. Avancer d'une barre — génère un MarketEvent
            has_data = self._data.update_bars()
            if not has_data:
                break

            # 2. Traiter tous les événements de la queue (MarketEvent → Signals → Orders → Fills)
            current_bar_event: Optional[MarketEvent] = None
            while not self._queue.empty():
                event = self._queue.get()
                if event.type == EventType.MARKET:
                    current_bar_event = event   # saved for equity update below
                self._dispatch(event)

            # 3. Equity enregistrée APRÈS tous les fills de cette barre (exits + entries).
            #    Ceci corrige le décalage d'1 barre : dans l'ancienne version l'equity était
            #    enregistrée à l'intérieur de _on_market, avant que les fills d'entrée des
            #    nouveaux signaux soient traités.
            if current_bar_event is not None:
                self._portfolio.on_market(current_bar_event)

        # 4. Fermer de force les positions encore ouvertes en fin de backtest.
        #    Sans ça, les positions ouvertes à la dernière barre n'apparaissent jamais
        #    dans la liste des trades et causent une equity non-plate sans trade visible.
        self._close_remaining_positions()

        # 5. Corriger le dernier point de l'equity curve.
        #    on_market() a été appelé AVANT _close_remaining_positions(), donc les
        #    commissions de sortie end_of_backtest ne sont pas reflétées.
        #    On écrase la dernière entrée avec le cash final (toutes positions fermées).
        if self._portfolio._equity_history:
            last_ts = self._portfolio._equity_history[-1][0]
            self._portfolio._equity_history[-1] = (last_ts, self._portfolio._cash)

        finished_at = datetime.utcnow()

        # Sauvegarder le log d'audit
        self._write_audit_log()

        # Calculer les métriques
        metrics = compute_metrics(
            equity_curve=self._portfolio.equity_curve,
            trades=self._portfolio.trades,
            initial_capital=self._initial_capital,
        )

        logger.info(
            f"Backtest {self._run_id} terminé — "
            f"{metrics.get('n_trades', 0)} trades, "
            f"rendement {metrics.get('total_return_pct', 0):+.2f}%"
        )

        return BacktestResult(
            equity_curve=self._portfolio.equity_curve,
            trades=self._portfolio.trades,
            metrics=metrics,
            run_id=self._run_id,
            started_at=started_at,
            finished_at=finished_at,
        )

    # -----------------------------------------------------------------------
    # Dispatch des événements
    # -----------------------------------------------------------------------

    def _dispatch(self, event) -> None:
        if event.type == EventType.MARKET:
            self._on_market(event)
        elif event.type == EventType.SIGNAL:
            self._on_signal(event)
        elif event.type == EventType.ORDER:
            self._on_order(event)
        elif event.type == EventType.FILL:
            self._on_fill(event)

    def _on_market(self, event: MarketEvent) -> None:
        # 2a. Vérifier les stops/TP et les exécuter IMMÉDIATEMENT avant les signaux.
        #     Raison : si stop ET signal de sortie se déclenchent sur la même barre,
        #     on doit s'assurer que la position est déjà fermée quand on_bar() évalue
        #     les conditions — sinon le signal génère un 2e SELL qui ouvre un SHORT.
        bars = {s: self._data.get_latest_bar(s) for s in event.symbols
                if self._data.get_latest_bar(s) is not None}
        exit_orders = self._risk.check_exits(self._portfolio, bars)
        for order in exit_orders:
            self._on_order(order)           # exécute → ajoute le FILL dans la queue
        # Vider les FILL d'exit avant on_bar()
        while not self._queue.empty():
            self._dispatch(self._queue.get())

        # 2b. Appeler on_bar() de chaque stratégie sur chaque symbole
        for symbol in event.symbols:
            bar = self._data.get_latest_bar(symbol)
            if bar is not None:
                for strategy in self._strategies:
                    try:
                        strategy.on_bar(symbol, bar)
                    except ValueError:
                        # Pas assez de données pour les indicateurs — normal en début de série
                        pass

        # Note : l'equity curve est désormais mise à jour dans run() après que tous
        # les fills (y compris les entrées de on_bar) aient été traités.

        # Log
        self._event_log.append({
            "type":      "MARKET",
            "timestamp": event.timestamp.isoformat(),
            "symbols":   event.symbols,
        })

    def _on_signal(self, event: SignalEvent) -> None:
        # Warmup period: discard signals before trade_start_date
        if self._trade_start is not None and event.timestamp < self._trade_start:
            return
        bar = self._data.get_latest_bar(event.symbol)
        orders = self._risk.validate_order(event, self._portfolio, bar)

        self._event_log.append({
            "type":               "SIGNAL",
            "timestamp":          event.timestamp.isoformat(),
            "strategy_id":        event.strategy_id,
            "symbol":             event.symbol,
            "direction":          event.direction.value,
            "position_size":      event.position_size,
            "stop_loss":          event.stop_loss,
            "take_profit":        event.take_profit,
            "indicator_snapshot": event.indicator_snapshot,
            "order_generated":    len(orders) > 0,
        })

        for order in orders:
            self._queue.put(order)

    def _on_order(self, event: OrderEvent) -> None:
        self._event_log.append({
            "type":              "ORDER",
            "timestamp":         event.timestamp.isoformat(),
            "symbol":            event.symbol,
            "side":              event.side.value,
            "quantity":          round(event.quantity, 6),
            "order_type":        event.order_type.value,
            "stop_loss_price":   event.stop_loss_price,
            "take_profit_price": event.take_profit_price,
        })
        self._execution.execute_order(event)

    def _on_fill(self, event: FillEvent) -> None:
        self._event_log.append({
            "type":       "FILL",
            "timestamp":  event.timestamp.isoformat(),
            "symbol":     event.symbol,
            "side":       event.side.value,
            "quantity":   round(event.quantity, 6),
            "fill_price": round(event.fill_price, 6),
            "commission": round(event.commission, 4),
            "notional":   round(event.notional, 2),
        })
        self._portfolio.on_fill(event)

    # -----------------------------------------------------------------------
    # Fermeture forcée de fin de backtest
    # -----------------------------------------------------------------------

    def _close_remaining_positions(self) -> None:
        """
        Ferme toutes les positions encore ouvertes à la dernière barre disponible.

        Sans cette étape, une position ouverte mais non encore clôturée au moment
        où les données s'épuisent n'apparaît jamais dans result.trades — ce qui
        crée une equity curve non-plate sur la période concernée sans aucun trade
        visible dans la table.

        Le fill est créé au prix de clôture de la dernière barre et est marqué
        exit_reason = "end_of_backtest" pour le distinguer des exits stratégiques.
        """
        from backtest.core.events import Direction, OrderEvent, OrderSide, OrderType, SignalEvent

        now = self._data.current_timestamp or datetime.utcnow()

        positions_to_close = (
            [(pos.symbol, pos, OrderSide.SELL) for pos in list(self._portfolio.long_positions.values())]
            + [(pos.symbol, pos, OrderSide.BUY)  for pos in list(self._portfolio.short_positions.values())]
        )

        for symbol, pos, side in positions_to_close:
            bar = self._data.get_latest_bar(symbol)
            if bar is None:
                continue
            direction = Direction.FLAT if side == OrderSide.SELL else Direction.COVER
            fake_signal = SignalEvent(
                timestamp=now,
                strategy_id="end_of_backtest",
                symbol=symbol,
                direction=direction,
                position_size=0.0,
                basket_id=pos.basket_id,
                indicator_snapshot={"_exit_reason": "end_of_backtest"},
            )
            fake_order = OrderEvent(
                timestamp=now,
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=side,
                quantity=pos.quantity,
                is_opening=False,
                basket_id=pos.basket_id,
                signal_ref=fake_signal,
            )
            self._execution.execute_order(fake_order)
            # Flush fills immediately so portfolio is up to date before next close
            while not self._queue.empty():
                ev = self._queue.get()
                if ev.type == EventType.FILL:
                    self._portfolio.on_fill(ev)

    # -----------------------------------------------------------------------
    # Audit log
    # -----------------------------------------------------------------------

    def _write_audit_log(self) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"{self._run_id}_audit.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "run_id":     self._run_id,
                    "n_events":   len(self._event_log),
                    "events":     self._event_log,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.info(f"Audit log : {path} ({len(self._event_log)} événements)")
