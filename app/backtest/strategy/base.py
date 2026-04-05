"""
strategy/base.py — Classe de base pour toutes les stratégies.

Écrire une nouvelle stratégie = hériter de BaseStrategy et implémenter on_bar().
Toute la complexité (events, orders, logs) est gérée par le moteur.

Exemple minimal :
    class MaCrossover(BaseStrategy):
        strategy_id  = "ma_crossover"
        position_size = 0.1
        stop_loss     = 0.02

        def on_bar(self, symbol: str, bar: pd.Series) -> None:
            fast = self.indicator("SMA", 10)
            slow = self.indicator("SMA", 50)
            if fast > slow:
                self.signal(symbol, "LONG", {"SMA_10": fast, "SMA_50": slow})
            elif fast < slow:
                self.signal(symbol, "FLAT")
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

import pandas as pd

from backtest.core.events import Direction, SignalEvent
from backtest.strategy.indicators import compute_indicator

if TYPE_CHECKING:
    from backtest.data.base import AbstractDataHandler
    from backtest.core.queue import EventQueue


class BaseStrategy(ABC):
    # -----------------------------------------------------------------------
    # Attributs de classe — à surcharger dans la stratégie concrète.
    # Aucune valeur "magique" : tout doit être explicite.
    # -----------------------------------------------------------------------

    strategy_id:    str            = "unnamed"
    position_size:  float          = 0.10    # fraction du capital, ex: 0.10 = 10%
    stop_loss:      Optional[float] = None   # fraction du prix, ex: 0.02 = 2%
    take_profit:    Optional[float] = None   # fraction du prix, ex: 0.05 = 5%
    execution_mode: str            = "netting"  # "netting" | "netting_delay" | "hedge"

    def __init__(
        self,
        data: "AbstractDataHandler",
        queue: "EventQueue",
    ) -> None:
        self._data  = data
        self._queue = queue

    # -----------------------------------------------------------------------
    # Méthode à implémenter
    # -----------------------------------------------------------------------

    @abstractmethod
    def on_bar(self, symbol: str, bar: pd.Series) -> None:
        """
        Appelé une fois par barre et par symbole.
        Utilisez self.indicator() pour les valeurs et self.signal() pour émettre.
        """

    # -----------------------------------------------------------------------
    # Helpers disponibles dans on_bar()
    # -----------------------------------------------------------------------

    def indicator(
        self,
        name: str,
        period: int,
        symbol: Optional[str] = None,
    ) -> float:
        """
        Calcule l'indicateur sur les données passées disponibles.

        Garantie no look-ahead : utilise uniquement get_latest_n_bars().
        Lève ValueError si les données sont insuffisantes — à gérer dans on_bar()
        avec un guard : if len(bars) < period: return

        Args:
            name:   Nom de l'indicateur (insensible à la casse). Ex: "SMA", "RSI"
            period: Période. Ex: 20
            symbol: Optionnel — utilise le premier symbole du handler par défaut.
        """
        target = symbol or self._data.symbol_list[0]
        # +1 pour les indicateurs qui ont besoin d'une barre précédente (ATR, RSI)
        bars = self._data.get_latest_n_bars(target, period + 1)
        return compute_indicator(name, bars, period)

    def signal(
        self,
        symbol: str,
        direction: Direction | str,
        indicator_snapshot: Optional[dict[str, float]] = None,
        *,
        position_size: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        basket_id: Optional[str] = None,
        basket_sl: Optional[float] = None,
        basket_tp: Optional[float] = None,
    ) -> None:
        """
        Émet un SignalEvent dans la queue du moteur.

        Les paramètres de risque (stop_loss, take_profit, position_size)
        sont lus depuis les attributs de classe — pas besoin de les passer ici
        sauf pour surcharger ponctuellement.

        Args:
            symbol:             Ticker de l'asset concerné.
            direction:          "LONG", "SHORT", "FLAT", "COVER" ou Direction enum.
            indicator_snapshot: Dict des valeurs d'indicateurs au moment du signal
                                (pour l'audit trail). Optionnel mais recommandé.
            position_size:      Surcharge ponctuelle de la taille de position.
            stop_loss:          Surcharge ponctuelle du stop loss (fraction du prix).
            take_profit:        Surcharge ponctuelle du take profit (fraction du prix).
            basket_id:          Identifiant du basket (None = position individuelle classique).
            basket_sl:          Stop loss au niveau basket (fraction du PnL du basket).
            basket_tp:          Take profit au niveau basket (fraction du PnL du basket).
        """
        if self._data.current_timestamp is None:
            return

        if isinstance(direction, str):
            direction = Direction[direction.upper()]

        _ps = position_size if position_size is not None else self.position_size
        # For basket positions, individual SL/TP defaults to None (basket handles them)
        _sl = stop_loss  if stop_loss  is not None else (None if basket_id else self.stop_loss)
        _tp = take_profit if take_profit is not None else (None if basket_id else self.take_profit)

        event = SignalEvent(
            timestamp=self._data.current_timestamp,
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=direction,
            position_size=_ps,
            stop_loss=_sl,
            take_profit=_tp,
            basket_id=basket_id,
            basket_sl=basket_sl,
            basket_tp=basket_tp,
            indicator_snapshot=indicator_snapshot or {},
        )
        self._queue.put(event)
