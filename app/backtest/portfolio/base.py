"""
portfolio/base.py — Interface abstraite + implémentation concrète SimplePortfolio.

SimplePortfolio :
- Capital partagé entre toutes les stratégies (pool commun)
- Positions LONG et SHORT gérées séparément par symbole
  → en mode NETTING : au plus une position par symbole (gérée par le RiskManager)
  → en mode HEDGE   : une position LONG ET une SHORT peuvent coexister sur le même symbole
- Equity curve mise à jour à chaque barre (mark-to-market)
- PnL calculé en devise de base
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import pandas as pd

from backtest.core.events import Direction, FillEvent, MarketEvent, OrderSide
from backtest.portfolio.position import Position, TradeRecord

if TYPE_CHECKING:
    from backtest.data.base import AbstractDataHandler


# ---------------------------------------------------------------------------
# Interface abstraite
# ---------------------------------------------------------------------------

class AbstractPortfolio(ABC):

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None:
        """Met à jour positions et cash suite à un fill."""

    @abstractmethod
    def on_market(self, event: MarketEvent) -> None:
        """Appelé à chaque barre — met à jour l'equity curve."""

    @property
    @abstractmethod
    def equity(self) -> float:
        """Capital total courant (cash + mark-to-market des positions)."""

    @property
    @abstractmethod
    def cash(self) -> float:
        """Liquidités disponibles."""

    @property
    @abstractmethod
    def long_positions(self) -> dict[str, Position]:
        """Positions LONG ouvertes par symbole."""

    @property
    @abstractmethod
    def short_positions(self) -> dict[str, Position]:
        """Positions SHORT ouvertes par symbole."""

    @property
    @abstractmethod
    def basket_entries(self) -> dict[str, float]:
        """basket_id → total entry notional."""

    @property
    @abstractmethod
    def basket_params(self) -> dict[str, dict]:
        """basket_id → {sl, tp}."""

    @property
    @abstractmethod
    def equity_curve(self) -> pd.Series:
        """Série temporelle de l'équity (index = datetime, valeurs = float)."""

    @property
    @abstractmethod
    def trades(self) -> list[TradeRecord]:
        """Tous les trades clôturés."""

    # Compat helper — retourne toutes les positions ouvertes (LONG + SHORT)
    @property
    def positions(self) -> dict[str, Position]:
        """
        Vue combinée LONG + SHORT.
        En mode NETTING il n'y a jamais de collision (au plus une position par symbole).
        En mode HEDGE, si les deux existent, LONG prend la priorité dans ce dict
        — utiliser long_positions / short_positions directement pour l'accès précis.
        """
        combined = dict(self.short_positions)
        combined.update(self.long_positions)
        return combined


# ---------------------------------------------------------------------------
# Implémentation concrète
# ---------------------------------------------------------------------------

class SimplePortfolio(AbstractPortfolio):
    """
    Portfolio simple à capital partagé.
    Positions LONG et SHORT gérées dans deux dicts séparés pour supporter
    aussi bien le mode netting (une seule direction à la fois par symbole)
    que le mode hedge (les deux coexistent).
    """

    def __init__(
        self,
        initial_capital: float,
        data: "AbstractDataHandler",
        execution_mode: str = "netting",
    ) -> None:
        self._execution_mode = execution_mode
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._data = data
        self._long_positions:  dict[str, Position] = {}
        self._short_positions: dict[str, Position] = {}
        self._equity_history: list[tuple[datetime, float]] = []
        self._trades: list[TradeRecord] = []
        self._basket_entries: dict[str, float] = {}   # basket_id → total entry notional
        self._basket_params:  dict[str, dict]  = {}   # basket_id → {sl, tp}

    def _pos_key(self, symbol: str, basket_id: Optional[str] = None) -> str:
        """
        Position dictionary key.
        Hedge mode + basket_id: 'basket_id:symbol'  (independent per-basket tracking)
        All other cases:         'symbol'
        """
        if self._execution_mode == "hedge" and basket_id:
            return f"{basket_id}:{symbol}"
        return symbol

    def get_long_position(self, symbol: str, basket_id: Optional[str] = None) -> Optional[Position]:
        return self._long_positions.get(self._pos_key(symbol, basket_id))

    def get_short_position(self, symbol: str, basket_id: Optional[str] = None) -> Optional[Position]:
        return self._short_positions.get(self._pos_key(symbol, basket_id))

    # -----------------------------------------------------------------------
    # Événements
    # -----------------------------------------------------------------------

    def on_fill(self, event: FillEvent) -> None:
        if event.side == OrderSide.BUY:
            self._handle_buy(event)
        elif event.side == OrderSide.SELL:
            self._handle_sell(event)

    def _handle_buy(self, event: FillEvent) -> None:
        """
        BUY fill = ouverture LONG (is_opening=True) ou fermeture SHORT (is_opening=False).
        On utilise le flag explicite — jamais l'existence d'une position —
        pour supporter le mode Hedge où LONG et SHORT coexistent sur le même symbole.
        """
        symbol    = event.symbol
        is_opening = event.order_ref.is_opening if event.order_ref else False

        if is_opening:
            # ── Ouverture LONG ───────────────────────────────────────────────
            cost = event.quantity * event.fill_price + event.commission
            self._cash -= cost
            stop_price = event.order_ref.stop_loss_price   if event.order_ref else None
            tp_price   = event.order_ref.take_profit_price if event.order_ref else None
            basket_id  = event.order_ref.basket_id         if event.order_ref else None
            if basket_id:
                notional = event.quantity * event.fill_price
                self._basket_entries[basket_id] = self._basket_entries.get(basket_id, 0.0) + notional
                if basket_id not in self._basket_params:
                    self._basket_params[basket_id] = {
                        "sl": event.order_ref.basket_sl,
                        "tp": event.order_ref.basket_tp,
                    }
            entry_snapshot = (
                event.order_ref.signal_ref.indicator_snapshot
                if event.order_ref and event.order_ref.signal_ref else {}
            )
            _key = self._pos_key(symbol, basket_id)
            self._long_positions[_key] = Position(
                symbol=symbol,
                direction=Direction.LONG,
                quantity=event.quantity,
                entry_price=event.fill_price,
                entry_time=event.timestamp,
                entry_commission=event.commission,
                stop_loss_price=stop_price,
                take_profit_price=tp_price,
                basket_id=basket_id,
                entry_snapshot=entry_snapshot,
            )
        else:
            # ── Fermeture SHORT (buy-to-cover) ───────────────────────────────
            _basket_id = event.order_ref.basket_id if event.order_ref else None
            _key = self._pos_key(symbol, _basket_id)
            pos = self._short_positions.pop(_key, None)
            if pos is None:
                return  # position already closed (e.g. duplicate exit signal)
            # Cash deduction AFTER confirming position exists — prevents double-deduct
            # when both reversal (LONG) and COVER signals fire on the same bar.
            self._cash -= event.quantity * event.fill_price + event.commission
            exit_reason = self._get_exit_reason(event)
            pnl     = (pos.entry_price - event.fill_price) * event.quantity
            net_pnl = pnl - event.commission - pos.entry_commission
            pnl_pct = net_pnl / (pos.entry_price * pos.quantity) if pos.entry_price else 0.0
            self._trades.append(TradeRecord(
                symbol=symbol,
                direction=Direction.SHORT,
                entry_time=pos.entry_time,
                exit_time=event.timestamp,
                entry_price=pos.entry_price,
                exit_price=event.fill_price,
                quantity=event.quantity,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                total_commission=event.commission + pos.entry_commission,
                exit_reason=exit_reason,
                strategy_id=event.order_ref.signal_ref.strategy_id
                    if event.order_ref and event.order_ref.signal_ref else "",
                basket_id=pos.basket_id,
                indicator_snapshot=pos.entry_snapshot,  # entry snapshot, not exit
            ))
            basket_id = pos.basket_id
            if basket_id:
                still_open = any(
                    p.basket_id == basket_id
                    for p in list(self._long_positions.values()) + list(self._short_positions.values())
                )
                if not still_open:
                    self._basket_entries.pop(basket_id, None)
                    self._basket_params.pop(basket_id, None)

    def _handle_sell(self, event: FillEvent) -> None:
        """
        SELL fill = ouverture SHORT (is_opening=True) ou fermeture LONG (is_opening=False).
        On utilise le flag explicite — jamais l'existence d'une position —
        pour supporter le mode Hedge où LONG et SHORT coexistent sur le même symbole.
        """
        symbol     = event.symbol
        is_opening = event.order_ref.is_opening if event.order_ref else False

        if is_opening:
            # ── Ouverture SHORT (sell-short) ─────────────────────────────────
            self._cash += event.quantity * event.fill_price - event.commission
            stop_price = event.order_ref.stop_loss_price   if event.order_ref else None
            tp_price   = event.order_ref.take_profit_price if event.order_ref else None
            basket_id  = event.order_ref.basket_id         if event.order_ref else None
            if basket_id:
                notional = event.quantity * event.fill_price
                self._basket_entries[basket_id] = self._basket_entries.get(basket_id, 0.0) + notional
                if basket_id not in self._basket_params:
                    self._basket_params[basket_id] = {
                        "sl": event.order_ref.basket_sl,
                        "tp": event.order_ref.basket_tp,
                    }
            entry_snapshot = (
                event.order_ref.signal_ref.indicator_snapshot
                if event.order_ref and event.order_ref.signal_ref else {}
            )
            _key = self._pos_key(symbol, basket_id)
            self._short_positions[_key] = Position(
                symbol=symbol,
                direction=Direction.SHORT,
                quantity=event.quantity,
                entry_price=event.fill_price,
                entry_time=event.timestamp,
                entry_commission=event.commission,
                stop_loss_price=stop_price,
                take_profit_price=tp_price,
                basket_id=basket_id,
                entry_snapshot=entry_snapshot,
            )
        else:
            # ── Fermeture LONG (sell-to-close) ───────────────────────────────
            _basket_id = event.order_ref.basket_id if event.order_ref else None
            _key = self._pos_key(symbol, _basket_id)
            pos = self._long_positions.pop(_key, None)
            if pos is None:
                return  # position already closed (e.g. duplicate exit signal)
            self._cash += event.quantity * event.fill_price - event.commission
            exit_reason = self._get_exit_reason(event)
            pnl     = (event.fill_price - pos.entry_price) * event.quantity
            net_pnl = pnl - event.commission - pos.entry_commission
            pnl_pct = net_pnl / (pos.entry_price * pos.quantity) if pos.entry_price else 0.0
            self._trades.append(TradeRecord(
                symbol=symbol,
                direction=Direction.LONG,
                entry_time=pos.entry_time,
                exit_time=event.timestamp,
                entry_price=pos.entry_price,
                exit_price=event.fill_price,
                quantity=event.quantity,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                total_commission=event.commission + pos.entry_commission,
                exit_reason=exit_reason,
                strategy_id=event.order_ref.signal_ref.strategy_id
                    if event.order_ref and event.order_ref.signal_ref else "",
                basket_id=pos.basket_id,
                indicator_snapshot=pos.entry_snapshot,  # entry snapshot, not exit
            ))
            basket_id = pos.basket_id
            if basket_id:
                still_open = any(
                    p.basket_id == basket_id
                    for p in list(self._long_positions.values()) + list(self._short_positions.values())
                )
                if not still_open:
                    self._basket_entries.pop(basket_id, None)
                    self._basket_params.pop(basket_id, None)

    def on_market(self, event: MarketEvent) -> None:
        eq = self._compute_equity(event.timestamp)
        self._equity_history.append((event.timestamp, eq))

    def _compute_equity(self, timestamp: datetime) -> float:
        """
        Somme le cash + toutes les positions open (LONG et SHORT séparément).
        On itère sur chaque dict indépendamment — ne pas merger en un seul dict
        car en mode Hedge un symbole peut avoir un LONG ET un SHORT simultanément
        et le merge {**long, **short} ferait silencieusement disparaître le LONG.
        """
        equity = self._cash
        for pos in self._long_positions.values():
            bar = self._data.get_latest_bar(pos.symbol)
            if bar is not None:
                equity += pos.market_value(bar["close"])
        for pos in self._short_positions.values():
            bar = self._data.get_latest_bar(pos.symbol)
            if bar is not None:
                equity += pos.market_value(bar["close"])
        return equity

    @staticmethod
    def _get_exit_reason(event: FillEvent) -> str:
        if event.order_ref is None:
            return "signal"
        signal = event.order_ref.signal_ref
        if signal is None:
            return "signal"
        snap = signal.indicator_snapshot
        if snap.get("_exit_reason"):
            return snap["_exit_reason"]
        # Closing fill driven by an entry signal in the opposite direction → reversal
        if not event.order_ref.is_opening and signal.direction not in (
            Direction.FLAT, Direction.COVER
        ):
            return "signal_reverse"
        return "signal"

    # -----------------------------------------------------------------------
    # Propriétés
    # -----------------------------------------------------------------------

    @property
    def equity(self) -> float:
        return self._equity_history[-1][1] if self._equity_history else self._cash

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def initial_capital(self) -> float:
        return self._initial_capital

    @property
    def long_positions(self) -> dict[str, Position]:
        return self._long_positions

    @property
    def short_positions(self) -> dict[str, Position]:
        return self._short_positions

    @property
    def basket_entries(self) -> dict[str, float]:
        return self._basket_entries

    @property
    def basket_params(self) -> dict[str, dict]:
        return self._basket_params

    @property
    def equity_curve(self) -> pd.Series:
        if not self._equity_history:
            return pd.Series(dtype=float)
        timestamps, values = zip(*self._equity_history)
        return pd.Series(values, index=pd.DatetimeIndex(timestamps), name="equity")

    @property
    def trades(self) -> list[TradeRecord]:
        return self._trades
