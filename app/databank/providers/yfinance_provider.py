"""
databank/providers/yfinance_provider.py — Téléchargement via Yahoo Finance.

Nécessite : pip install yfinance

Tickers valides :
  Indices  : ^GSPC (S&P500), ^IXIC (Nasdaq), ^GDAXI (DAX), ^FCHI (CAC40),
             ^FTSE (FTSE100), ^N225 (Nikkei), ^HSI (Hang Seng)
  Actions  : AAPL, MSFT, AMZN, GOOGL, META, TSLA, etc.
  FX       : EURUSD=X, GBPUSD=X, USDJPY=X, etc.
  Crypto   : BTC-USD, ETH-USD, etc.
  VIX      : ^VIX
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd

from databank.providers.base import AbstractProvider


class YFinanceProvider(AbstractProvider):

    @property
    def name(self) -> str:
        return "yfinance"

    def fetch(
        self,
        ticker: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError(
                "yfinance n'est pas installé.\n"
                "Installez-le avec : pip install yfinance"
            )

        params: dict = {"auto_adjust": True, "progress": False}
        if start:
            params["start"] = start.strftime("%Y-%m-%d")
            if end:
                params["end"] = end.strftime("%Y-%m-%d")
        else:
            # Sans date de début, les versions recentes de yfinance retournent
            # seulement 1 mois par défaut — forcer period="max" pour l'historique complet.
            params["period"] = "max"

        print(f"  Téléchargement de {ticker} depuis Yahoo Finance...")
        df = yf.download(ticker, **params)

        if df.empty:
            raise ValueError(
                f"Aucune donnée retournée pour '{ticker}' par Yahoo Finance.\n"
                f"Vérifiez le ticker (ex: ^GSPC pour le S&P500, BTC-USD pour le Bitcoin)."
            )

        # Normalisation vers le format interne
        # Les versions recentes de yfinance retournent un MultiIndex (Price, Ticker)
        # pour les telechargements meme sur un seul symbole → on aplatit d'abord.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() if isinstance(c, str) else str(c[0]).lower()
                      for c in df.columns]
        col_map = {
            "adj close": "close",
            "open": "open", "high": "high", "low": "low",
            "close": "close", "volume": "volume",
        }
        df = df.rename(columns=col_map)

        keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[keep].astype(float)
        df.index = pd.to_datetime(df.index)
        df.index.name = "timestamp"
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df = df.dropna(subset=["close"])

        print(f"  ✓  {len(df):,} barres récupérées : {df.index[0].date()} → {df.index[-1].date()}")
        return df
