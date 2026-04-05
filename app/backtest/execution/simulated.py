"""
execution/simulated.py — ExecutionHandler simulé.

Règles de simulation :
- Fill au prix de clôture de la barre courante (close du MarketEvent en cours).
- Commission calculée selon CommissionConfig (rate * notional, minimum garanti).
- Pas de slippage dans cette version (peut être ajouté facilement).
- Pas de rejet d'ordre (liquidité supposée infinie).

Déterminisme strict : pour un même OrderEvent et un même CSV,
le FillEvent produit sera identique à chaque exécution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from backtest.core.events import FillEvent, OrderEvent
from backtest.core.queue import EventQueue
from backtest.data.base import AbstractDataHandler
from backtest.execution.base import AbstractExecutionHandler

if TYPE_CHECKING:
    pass


@dataclass
class CommissionConfig:
    """
    Modèle de commission simple et configurable.

    rate    : fraction de la valeur notionnelle (0.001 = 0.1%)
    minimum : commission minimale par trade (en devise de base)

    Exemple : rate=0.001, minimum=1.0
        → Trade de 500 USD : commission = max(0.5, 1.0) = 1.0 USD
        → Trade de 5000 USD : commission = max(5.0, 1.0) = 5.0 USD
    """
    rate:    float = 0.001   # 0.1% par défaut
    minimum: float = 0.0     # pas de minimum par défaut

    def calculate(self, notional: float) -> float:
        return max(self.minimum, abs(notional) * self.rate)


class SimulatedExecutionHandler(AbstractExecutionHandler):
    """
    Exécution simulée au close de la barre courante.
    Convient pour un backtest end-of-day.
    """

    def __init__(
        self,
        data: AbstractDataHandler,
        queue: EventQueue,
        commission: CommissionConfig,
    ) -> None:
        self._data       = data
        self._queue      = queue
        self._commission = commission

    def execute_order(self, event: OrderEvent) -> None:
        symbol = event.symbol
        bar = self._data.get_latest_bar(symbol)

        if bar is None:
            # Pas de données pour ce symbole à cet instant — ordre ignoré
            return

        fill_price = float(bar["close"])
        notional   = fill_price * event.quantity
        commission = self._commission.calculate(notional)

        # Utiliser le timestamp propre de la barre, pas current_timestamp du handler
        # (qui pourrait être celui du dernier symbole itéré en cas de multi-symbole)
        fill_ts = bar.name if isinstance(bar.name, (datetime, pd.Timestamp)) \
                  else self._data.current_timestamp

        fill = FillEvent(
            timestamp=fill_ts,
            symbol=symbol,
            side=event.side,
            quantity=event.quantity,
            fill_price=fill_price,
            commission=commission,
            order_ref=event,
        )
        self._queue.put(fill)
