"""
risk/base.py — Interface abstraite du RiskManager.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pandas as pd

from backtest.core.events import OrderEvent, SignalEvent

if TYPE_CHECKING:
    from backtest.portfolio.base import AbstractPortfolio


class AbstractRiskManager(ABC):
    """
    Validé avant chaque OrderEvent.
    Deux responsabilités :
    1. validate_order() — transformer un signal en ordre (ou rejeter)
    2. check_exits()   — surveiller les stops/TP sur les positions ouvertes
    """

    @abstractmethod
    def validate_order(
        self,
        signal: SignalEvent,
        portfolio: "AbstractPortfolio",
        bar: pd.Series,
    ) -> list[OrderEvent]:
        """
        Retourne la liste d'OrderEvents à exécuter (peut être vide si signal rejeté).
        Pour un signal simple : liste d'un élément.
        Pour une inversion de direction (SHORT→LONG) : [close_order, open_order]
        exécutés sur la même barre, sans décalage d'un jour.
        """

    @abstractmethod
    def check_exits(
        self,
        portfolio: "AbstractPortfolio",
        bars: dict[str, pd.Series],
    ) -> list[OrderEvent]:
        """
        Vérifie si des stops ou TP sont atteints sur les positions ouvertes.
        Appelé à chaque MarketEvent, AVANT on_bar() des stratégies.
        Retourne la liste des ordres de sortie à exécuter.
        """
