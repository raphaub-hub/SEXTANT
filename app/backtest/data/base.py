"""
data/base.py — Interface abstraite du DataHandler.

Contrat strict :
- get_latest_bar() et get_latest_n_bars() ne retournent JAMAIS de données futures.
- update_bars() avance d'exactement une barre et pousse un MarketEvent.
- Aucune composante ne doit jamais accéder aux données autrement que via ces méthodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class AbstractDataHandler(ABC):

    @property
    @abstractmethod
    def symbol_list(self) -> list[str]: ...

    @property
    @abstractmethod
    def current_timestamp(self) -> Optional[datetime]: ...

    @abstractmethod
    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        """
        Retourne la barre courante (la plus récente reçue).
        Colonnes garanties : open, high, low, close, volume.
        Index = timestamp.
        """

    @abstractmethod
    def get_latest_n_bars(self, symbol: str, n: int) -> pd.DataFrame:
        """
        Retourne les n dernières barres closes (inclut la barre courante).
        Utilisé par les indicateurs — ne contient JAMAIS de données futures.
        Retourne un DataFrame vide si pas assez de données.
        """

    @abstractmethod
    def update_bars(self) -> bool:
        """
        Avance d'une barre sur tous les symboles.
        Pousse un MarketEvent dans la queue.
        Retourne False si plus de données disponibles.
        """
