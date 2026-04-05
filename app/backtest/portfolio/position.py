"""
portfolio/position.py — Représentation d'une position ouverte et d'un trade clôturé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backtest.core.events import Direction


@dataclass
class Position:
    """
    Position ouverte sur un asset.
    Créée à l'entrée (FillEvent BUY/SELL), détruite à la sortie.
    """
    symbol:            str
    direction:         Direction      # LONG ou SHORT
    quantity:          float          # unités détenues
    entry_price:       float          # prix moyen d'entrée (fill price)
    entry_time:        datetime
    entry_commission:  float = 0.0
    stop_loss_price:   Optional[float] = None
    take_profit_price: Optional[float] = None
    basket_id:         Optional[str]   = None
    entry_snapshot:    dict            = field(default_factory=dict)  # indicators at entry

    def unrealized_pnl(self, current_price: float) -> float:
        """PnL non réalisé au prix courant."""
        if self.direction == Direction.LONG:
            return (current_price - self.entry_price) * self.quantity
        elif self.direction == Direction.SHORT:
            return (self.entry_price - current_price) * self.quantity
        return 0.0

    def market_value(self, current_price: float) -> float:
        """
        Valeur mark-to-market signée de la position.

        LONG  : +quantity × price  (actif détenu)
        SHORT : −quantity × price  (passif — le cash reçu à l'ouverture
                                    est déjà dans self._cash ; on soustrait
                                    la valeur courante du passif)
        """
        if self.direction == Direction.SHORT:
            return -self.quantity * current_price
        return self.quantity * current_price

    def is_stop_triggered(self, current_price: float) -> bool:
        if self.stop_loss_price is None:
            return False
        if self.direction == Direction.LONG:
            return current_price <= self.stop_loss_price
        elif self.direction == Direction.SHORT:
            return current_price >= self.stop_loss_price
        return False

    def is_tp_triggered(self, current_price: float) -> bool:
        if self.take_profit_price is None:
            return False
        if self.direction == Direction.LONG:
            return current_price >= self.take_profit_price
        elif self.direction == Direction.SHORT:
            return current_price <= self.take_profit_price
        return False


@dataclass
class TradeRecord:
    """
    Trade clôturé — enregistrement complet pour l'audit trail et les métriques.
    Traçabilité : indicator_snapshot permet de vérifier la décision à la main.
    """
    symbol:             str
    direction:          Direction
    entry_time:         datetime
    exit_time:          datetime
    entry_price:        float
    exit_price:         float
    quantity:           float
    pnl:                float          # net de commissions
    pnl_pct:            float          # en fraction (0.05 = +5%)
    total_commission:   float
    exit_reason:        str            # "signal" | "stop_loss" | "take_profit"
    strategy_id:        str
    basket_id:          Optional[str]   = None
    indicator_snapshot: dict[str, float] = field(default_factory=dict)

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    def to_dict(self) -> dict:
        return {
            "symbol":             self.symbol,
            "direction":          self.direction.value,
            "entry_time":         self.entry_time.isoformat(),
            "exit_time":          self.exit_time.isoformat(),
            "entry_price":        round(self.entry_price, 6),
            "exit_price":         round(self.exit_price, 6),
            "quantity":           round(self.quantity, 6),
            "pnl":                round(self.pnl, 4),
            "pnl_pct":            round(self.pnl_pct * 100, 4),
            "total_commission":   round(self.total_commission, 4),
            "exit_reason":        self.exit_reason,
            "strategy_id":        self.strategy_id,
            "basket_id":          self.basket_id,
            "indicator_snapshot": {k: round(v, 6) for k, v in self.indicator_snapshot.items()},
        }
