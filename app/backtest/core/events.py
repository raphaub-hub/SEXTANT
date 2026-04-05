"""
events.py — Les 4 types d'événements du moteur.

Flux : MarketEvent → SignalEvent → OrderEvent → FillEvent

Chaque événement est immutable et contient toutes les informations
nécessaires pour reconstituer la décision a posteriori (audit trail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EventType(Enum):
    MARKET = "MARKET"
    SIGNAL = "SIGNAL"
    ORDER  = "ORDER"
    FILL   = "FILL"


class Direction(Enum):
    """
    Direction d'un signal de stratégie.

    LONG  — ouvrir / maintenir une position longue
    SHORT — ouvrir / maintenir une position courte
    FLAT  — fermer la position LONG existante (ou l'unique position en mode netting)
    COVER — fermer la position SHORT existante
              En mode HEDGE, FLAT et COVER sont indépendants.
              En mode NETTING, COVER est synonyme de FLAT (une seule position possible).
    """
    LONG  = "LONG"
    SHORT = "SHORT"
    FLAT  = "FLAT"
    COVER = "COVER"


class OrderSide(Enum):
    """Sens d'un ordre / fill — BUY ou SELL."""
    BUY  = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"


# ---------------------------------------------------------------------------
# Événements
# ---------------------------------------------------------------------------

@dataclass
class Event:
    timestamp: datetime
    type: EventType = field(init=False)


@dataclass
class MarketEvent(Event):
    """
    Nouvelle barre disponible pour un ensemble de symboles.
    Déclenché par DataHandler.update_bars() à chaque avancée.
    """
    symbols: list[str]
    type: EventType = field(default=EventType.MARKET, init=False)


@dataclass
class SignalEvent(Event):
    """
    Émis par une stratégie via self.signal().
    Pas encore un ordre — le RiskManager décide quoi en faire.

    indicator_snapshot : valeurs exactes des indicateurs au moment du signal
                         → permet de rejouer et vérifier la décision.
    """
    strategy_id:        str
    symbol:             str
    direction:          Direction
    position_size:      float                    # fraction du capital (ex: 0.1)
    stop_loss:          Optional[float] = None   # fraction du prix d'entrée (ex: 0.02)
    take_profit:        Optional[float] = None   # fraction du prix d'entrée (ex: 0.05)
    basket_id:          Optional[str]   = None   # None = single-asset (classic)
    basket_sl:          Optional[float] = None   # basket-level stop loss fraction
    basket_tp:          Optional[float] = None   # basket-level take profit fraction
    indicator_snapshot: dict[str, float] = field(default_factory=dict)
    type: EventType = field(default=EventType.SIGNAL, init=False)


@dataclass
class OrderEvent(Event):
    """
    Émis par le RiskManager après validation du signal.
    Contient la quantité exacte et les prix de stop/TP calculés.

    is_opening : True  → ordre d'ouverture d'une nouvelle position
                 False → ordre de fermeture d'une position existante
    Le portfolio utilise ce flag (jamais l'existence d'une position) pour
    distinguer BUY-to-open-long de BUY-to-cover-short, et SELL-to-close-long
    de SELL-to-open-short. Critique en mode Hedge où les deux coexistent.
    """
    symbol:            str
    order_type:        OrderType
    side:              OrderSide     # BUY ou SELL
    quantity:          float         # en unités de l'asset
    is_opening:        bool          = False  # True = ouvrir, False = fermer
    stop_loss_price:   Optional[float] = None
    take_profit_price: Optional[float] = None
    basket_id:         Optional[str]   = None
    basket_sl:         Optional[float] = None
    basket_tp:         Optional[float] = None
    signal_ref:        Optional[SignalEvent] = None
    type: EventType = field(default=EventType.ORDER, init=False)


@dataclass
class FillEvent(Event):
    """
    Émis par l'ExecutionHandler — trade réellement exécuté.
    Référence à l'ordre parent pour la traçabilité complète :
    FillEvent → OrderEvent → SignalEvent (avec indicator_snapshot).
    """
    symbol:     str
    side:       OrderSide
    quantity:   float
    fill_price: float
    commission: float
    order_ref:  Optional[OrderEvent] = None
    type: EventType = field(default=EventType.FILL, init=False)

    @property
    def notional(self) -> float:
        return self.quantity * self.fill_price

    @property
    def total_cost(self) -> float:
        return self.notional + self.commission
