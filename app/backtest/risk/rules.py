"""
risk/rules.py — Implémentation concrète du RiskManager.

StandardRiskManager :
- Position sizing : % fixe du capital courant
- Stop loss et take profit calculés au prix d'entrée
- Comportement paramétrable via ExecutionMode

──────────────────────────────────────────────────────────────────────────────
ExecutionMode.NETTING  (défaut)
    • Une seule position par symbole.
    • Inversion de direction (SHORT→LONG, LONG→SHORT) sur la MÊME barre :
      deux ordres retournés [close, open] — pas de décalage d'un jour.

ExecutionMode.NETTING_DELAY
    • Une seule position par symbole.
    • Inversion de direction sur la barre SUIVANTE :
      seul l'ordre de fermeture est retourné ; la stratégie réémettra
      l'entrée dans la nouvelle direction à la prochaine barre si les
      conditions sont toujours remplies.
    • Modélise le fait qu'on ne peut pas vendre et racheter au même close.

ExecutionMode.HEDGE
    • Les positions LONG et SHORT peuvent coexister sur le même symbole.
    • Signal LONG  → ouvre un LONG sans fermer le SHORT existant.
    • Signal SHORT → ouvre un SHORT sans fermer le LONG existant.
    • Signal FLAT  → ferme le LONG (si présent).
    • Signal COVER → ferme le SHORT (si présent).
    • Idéal pour les stratégies delta-neutre ou de couverture.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

import pandas as pd

from backtest.core.events import Direction, OrderEvent, OrderSide, OrderType, SignalEvent
from backtest.risk.base import AbstractRiskManager

if TYPE_CHECKING:
    from backtest.portfolio.base import AbstractPortfolio


class ExecutionMode(Enum):
    NETTING       = "netting"        # netting, inversion atomique même barre (défaut)
    NETTING_DELAY = "netting_delay"  # netting, inversion barre suivante
    HEDGE         = "hedge"          # long et short coexistent


class StandardRiskManager(AbstractRiskManager):

    def __init__(self, execution_mode: ExecutionMode = ExecutionMode.NETTING) -> None:
        self._mode = execution_mode

    # -----------------------------------------------------------------------
    # validate_order
    # -----------------------------------------------------------------------

    def validate_order(
        self,
        signal: SignalEvent,
        portfolio: "AbstractPortfolio",
        bar: Optional[pd.Series],
    ) -> list[OrderEvent]:
        if bar is None:
            return []

        symbol        = signal.symbol
        direction     = signal.direction
        current_price = float(bar["close"])

        # ── Position lookup — basket-aware in hedge mode ─────────────────────
        # In hedge mode: each basket tracks its own position independently.
        # In netting mode: one position per symbol regardless of basket.
        if self._mode == ExecutionMode.HEDGE:
            existing_long  = portfolio.get_long_position(symbol, signal.basket_id)
            existing_short = portfolio.get_short_position(symbol, signal.basket_id)
        else:
            existing_long  = portfolio.long_positions.get(symbol)
            existing_short = portfolio.short_positions.get(symbol)

        # ── FLAT : fermer la position LONG ───────────────────────────────────
        if direction == Direction.FLAT:
            if existing_long is not None:
                return [self._close_order(signal, existing_long, OrderSide.SELL)]
            # Compat netting : si pas de LONG mais un SHORT, on ferme le SHORT
            if existing_short is not None and self._mode != ExecutionMode.HEDGE:
                return [self._close_order(signal, existing_short, OrderSide.BUY)]
            return []

        # ── COVER : fermer la position SHORT ─────────────────────────────────
        if direction == Direction.COVER:
            if existing_short is not None:
                return [self._close_order(signal, existing_short, OrderSide.BUY)]
            # Compat netting : si pas de SHORT mais un LONG, on ferme le LONG
            if existing_long is not None and self._mode != ExecutionMode.HEDGE:
                return [self._close_order(signal, existing_long, OrderSide.SELL)]
            return []

        # ── LONG ─────────────────────────────────────────────────────────────
        if direction == Direction.LONG:
            if existing_long is not None:
                return []   # déjà long dans ce basket (hedge) ou ce symbole (netting)

            if self._mode == ExecutionMode.HEDGE:
                if existing_short is not None:
                    # Reversal intra-basket : fermer le SHORT du basket, ouvrir LONG
                    close = self._close_order(signal, existing_short, OrderSide.BUY)
                    open_ = self._open_orders(signal, portfolio.equity, current_price,
                                             OrderSide.BUY, Direction.LONG)
                    return [close] + open_
                return self._open_orders(signal, portfolio.equity, current_price,
                                        OrderSide.BUY, Direction.LONG)

            # NETTING / NETTING_DELAY
            if existing_short is not None:
                if self._mode == ExecutionMode.NETTING_DELAY:
                    return [self._close_order(signal, existing_short, OrderSide.BUY)]
                else:  # NETTING (same-bar reversal)
                    close = self._close_order(signal, existing_short, OrderSide.BUY)
                    open_ = self._open_orders(signal, portfolio.equity, current_price,
                                             OrderSide.BUY, Direction.LONG)
                    return [close] + open_

            return self._open_orders(signal, portfolio.equity, current_price,
                                    OrderSide.BUY, Direction.LONG)

        # ── SHORT ─────────────────────────────────────────────────────────────
        if direction == Direction.SHORT:
            if existing_short is not None:
                return []   # déjà short dans ce basket (hedge) ou ce symbole (netting)

            if self._mode == ExecutionMode.HEDGE:
                if existing_long is not None:
                    # Reversal intra-basket : fermer le LONG du basket, ouvrir SHORT
                    close = self._close_order(signal, existing_long, OrderSide.SELL)
                    open_ = self._open_orders(signal, portfolio.equity, current_price,
                                             OrderSide.SELL, Direction.SHORT)
                    return [close] + open_
                return self._open_orders(signal, portfolio.equity, current_price,
                                        OrderSide.SELL, Direction.SHORT)

            # NETTING / NETTING_DELAY
            if existing_long is not None:
                if self._mode == ExecutionMode.NETTING_DELAY:
                    return [self._close_order(signal, existing_long, OrderSide.SELL)]
                else:  # NETTING (same-bar reversal)
                    close = self._close_order(signal, existing_long, OrderSide.SELL)
                    open_ = self._open_orders(signal, portfolio.equity, current_price,
                                             OrderSide.SELL, Direction.SHORT)
                    return [close] + open_

            return self._open_orders(signal, portfolio.equity, current_price,
                                    OrderSide.SELL, Direction.SHORT)

        return []

    # -----------------------------------------------------------------------
    # check_exits  (stops / TP)
    # -----------------------------------------------------------------------

    def check_exits(
        self,
        portfolio: "AbstractPortfolio",
        bars: dict[str, pd.Series],
    ) -> list[OrderEvent]:
        orders: list[OrderEvent] = []
        now = next(iter(bars.values())).name if bars else datetime.utcnow()

        all_positions = [
            (pos.symbol, pos, OrderSide.SELL)
            for pos in portfolio.long_positions.values()
        ] + [
            (pos.symbol, pos, OrderSide.BUY)
            for pos in portfolio.short_positions.values()
        ]

        for symbol, pos, close_side in all_positions:
            if pos.basket_id:          # skip — handled by basket-level check below
                continue
            bar = bars.get(symbol)
            if bar is None:
                continue
            current_price = float(bar["close"])

            exit_reason: Optional[str] = None
            if pos.is_stop_triggered(current_price):
                exit_reason = "stop_loss"
            elif pos.is_tp_triggered(current_price):
                exit_reason = "take_profit"

            if exit_reason is not None:
                fake_signal = SignalEvent(
                    timestamp=now,
                    strategy_id=f"risk_manager:{exit_reason}",
                    symbol=symbol,
                    direction=Direction.FLAT,
                    position_size=0.0,
                    indicator_snapshot={"_exit_reason": exit_reason},
                )
                orders.append(OrderEvent(
                    timestamp=now,
                    symbol=symbol,
                    order_type=OrderType.MARKET,
                    side=close_side,
                    quantity=pos.quantity,
                    signal_ref=fake_signal,
                ))

        # ── Basket-level SL/TP ──────────────────────────────────────────────
        from collections import defaultdict
        basket_groups: dict[str, list] = defaultdict(list)
        for pos in portfolio.long_positions.values():
            if pos.basket_id:
                basket_groups[pos.basket_id].append((pos.symbol, pos, OrderSide.SELL))
        for pos in portfolio.short_positions.values():
            if pos.basket_id:
                basket_groups[pos.basket_id].append((pos.symbol, pos, OrderSide.BUY))

        for basket_id, members in basket_groups.items():
            params = portfolio.basket_params.get(basket_id, {})
            sl = params.get("sl")
            tp = params.get("tp")
            if sl is None and tp is None:
                continue
            entry_value = portfolio.basket_entries.get(basket_id, 0.0)
            if entry_value <= 0:
                continue
            # unrealized_pnl() est signé : positif = profit, négatif = perte,
            # que la position soit LONG ou SHORT — contrairement à qty*price
            # qui est toujours positif et donne un signe erroné pour les SHORTs.
            basket_pnl = sum(
                pos.unrealized_pnl(float(bars[sym]["close"]))
                for sym, pos, _ in members
                if sym in bars
            )
            pnl_pct = basket_pnl / entry_value if entry_value > 0 else 0.0
            reason = None
            if sl is not None and pnl_pct <= -sl:
                reason = "basket_stop_loss"
            elif tp is not None and pnl_pct >= tp:
                reason = "basket_take_profit"
            if reason:
                for sym, pos, close_side in members:
                    fake_signal = SignalEvent(
                        timestamp=now,
                        strategy_id=f"risk_manager:{reason}",
                        symbol=sym,
                        direction=Direction.FLAT,
                        position_size=0.0,
                        basket_id=basket_id,
                        indicator_snapshot={"_exit_reason": reason},
                    )
                    orders.append(OrderEvent(
                        timestamp=now,
                        symbol=sym,
                        order_type=OrderType.MARKET,
                        side=close_side,
                        quantity=pos.quantity,
                        basket_id=basket_id,
                        signal_ref=fake_signal,
                    ))

        return orders

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _close_order(
        signal: SignalEvent,
        pos: "Position",
        side: OrderSide,
    ) -> OrderEvent:
        return OrderEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            order_type=OrderType.MARKET,
            side=side,
            quantity=pos.quantity,
            stop_loss_price=None,
            take_profit_price=None,
            basket_id=pos.basket_id,
            signal_ref=signal,
        )

    @staticmethod
    def _open_orders(
        signal: SignalEvent,
        equity: float,
        current_price: float,
        side: OrderSide,
        direction: Direction,
    ) -> list[OrderEvent]:
        if current_price <= 0:
            return []
        quantity = max(0.0, equity * signal.position_size / current_price)
        if quantity <= 0:
            return []
        stop_price = StandardRiskManager._stop_price(direction, current_price, signal.stop_loss)
        tp_price   = StandardRiskManager._tp_price(direction, current_price, signal.take_profit)
        return [OrderEvent(
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            order_type=OrderType.MARKET,
            side=side,
            quantity=quantity,
            is_opening=True,
            stop_loss_price=stop_price,
            take_profit_price=tp_price,
            basket_id=signal.basket_id,
            basket_sl=signal.basket_sl,
            basket_tp=signal.basket_tp,
            signal_ref=signal,
        )]

    @staticmethod
    def _stop_price(
        direction: Direction,
        entry_price: float,
        stop_loss: Optional[float],
    ) -> Optional[float]:
        if stop_loss is None:
            return None
        if direction == Direction.LONG:
            return entry_price * (1.0 - stop_loss)
        return entry_price * (1.0 + stop_loss)

    @staticmethod
    def _tp_price(
        direction: Direction,
        entry_price: float,
        take_profit: Optional[float],
    ) -> Optional[float]:
        if take_profit is None:
            return None
        if direction == Direction.LONG:
            return entry_price * (1.0 + take_profit)
        return entry_price * (1.0 - take_profit)
