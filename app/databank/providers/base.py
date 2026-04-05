"""
databank/providers/base.py — Interface abstraite des fournisseurs de données.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class AbstractProvider(ABC):
    """
    Télécharge ou lit des données OHLCV et les retourne dans le format interne :
    index DatetimeIndex, colonnes open/high/low/close/volume, dtype float64.
    """

    @abstractmethod
    def fetch(
        self,
        ticker: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Retourne un DataFrame normalisé pour le ticker demandé.
        Lève ValueError si le ticker est inconnu ou les données indisponibles.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifiant du fournisseur (ex: 'yfinance', 'csv')."""
