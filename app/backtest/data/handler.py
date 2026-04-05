"""
data/handler.py — Implémentations concrètes du DataHandler.

DataBankHandler : lit les fichiers Parquet normalisés depuis market_data/.
  - Pre-charge tous les symboles primaires en mémoire.
  - Construit une grille de dates commune (intersection) pour garantir que
    tous les symboles sont toujours synchronisés sur le même timestamp.
  - Élimine le bug de desync multi-symboles de la v1 (new_timestamp
    écrasé à chaque itération du loop → timestamp du dernier symbole seulement).

RawCSVHandler : lit un CSV brut directement (tests rapides, symbole unique).

Les deux garantissent l'absence de look-ahead bias :
seules les barres passées sont accessibles via get_latest_n_bars().
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from backtest.core.events import MarketEvent
from backtest.core.queue import EventQueue
from backtest.data.base import AbstractDataHandler


# ---------------------------------------------------------------------------
# Handler principal — lit depuis la databank (Parquet normalisé)
# ---------------------------------------------------------------------------

class DataBankHandler(AbstractDataHandler):
    """
    Lit les fichiers Parquet produits par la databank.

    Garanties :
    - Tous les symboles primaires sont alignés sur une grille de dates
      commune (intersection) : impossible d'avoir des barres désynchronisées.
    - current_timestamp est toujours la date réelle de la barre courante,
      identique pour tous les symboles primaires.
    - Les séries compagnes (breadth, indicateurs) sont chargées lazily
      et filtrées par current_timestamp.
    """

    def __init__(
        self,
        symbols: list[str],
        queue: EventQueue,
        market_data_dir: Path,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> None:
        self._symbols = symbols
        self._queue   = queue
        self._market_data_dir = Path(market_data_dir)

        # _bars n'est plus utilisé — on slice directement _aligned avec _cursor

        self._current_timestamp: Optional[datetime] = None

        # Cache pour les séries compagnes (breadth, indicateurs)
        self._companion_frames: dict[str, Optional[pd.DataFrame]] = {}

        # Données pré-chargées et alignées sur la grille commune
        self._aligned: dict[str, pd.DataFrame] = {}
        self._dates: list = []   # liste triée des timestamps communs
        self._cursor: int = 0

        self._load_data(start_date, end_date)

    # -----------------------------------------------------------------------
    # Chargement initial
    # -----------------------------------------------------------------------

    def _find_parquet(self, symbol: str) -> Path:
        safe = symbol.replace("^", "_").replace("/", "_")
        for subdir in sorted(self._market_data_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                for candidate in [f"{safe}.parquet", f"{symbol}.parquet"]:
                    p = subdir / candidate
                    if p.exists():
                        return p
        raise FileNotFoundError(
            f"Aucun fichier Parquet trouvé pour '{symbol}' dans {self._market_data_dir}\n"
            f"Lancez : python -m databank.updater import --ticker {symbol}"
        )

    def _load_data(
        self,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> None:
        ts_start = pd.Timestamp(start_date).normalize() if start_date else None
        ts_end   = pd.Timestamp(end_date).normalize()   if end_date   else None

        raw: dict[str, pd.DataFrame] = {}
        for symbol in self._symbols:
            path = self._find_parquet(symbol)
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index).normalize()
            # Supprimer les doublons de date (garde la dernière barre)
            df = df[~df.index.duplicated(keep="last")].sort_index()
            if ts_start is not None:
                df = df[df.index >= ts_start]
            if ts_end is not None:
                df = df[df.index <= ts_end]
            if df.empty:
                raise ValueError(
                    f"Aucune donnée pour '{symbol}' sur la période demandée "
                    f"({start_date} → {end_date})."
                )
            raw[symbol] = df

        # ── Grille commune : intersection de tous les index de dates ──────────
        # Seules les dates où TOUS les symboles primaires ont une barre sont
        # conservées — élimine tout risque de désynchronisation.
        common: Optional[pd.DatetimeIndex] = None
        for df in raw.values():
            common = df.index if common is None else common.intersection(df.index)

        if common is None or len(common) == 0:
            raise ValueError(
                f"Aucune date commune trouvée entre tous les symboles "
                f"({', '.join(self._symbols)}) sur la période demandée."
            )

        # Aligner tous les frames sur la grille commune
        self._aligned = {s: raw[s].loc[common] for s in self._symbols}
        self._dates   = list(common)   # DatetimeIndex est déjà trié
        self._cursor  = 0

    # -----------------------------------------------------------------------
    # Interface AbstractDataHandler
    # -----------------------------------------------------------------------

    @property
    def symbol_list(self) -> list[str]:
        return self._symbols

    @property
    def current_timestamp(self) -> Optional[datetime]:
        return self._current_timestamp

    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        # Symbole primaire : slice du DataFrame aligné jusqu'au curseur courant
        if symbol in self._aligned and self._cursor > 0:
            return self._aligned[symbol].iloc[self._cursor - 1]
        # Série compagne (breadth, indicateur) : chargement lazy
        return self._get_companion_bar(symbol)

    def get_latest_n_bars(self, symbol: str, n: int) -> pd.DataFrame:
        # Symbole primaire — slice directe sur _aligned, pas de copie
        if symbol in self._aligned and self._cursor > 0:
            return self._aligned[symbol].iloc[max(0, self._cursor - n): self._cursor]
        # Série compagne
        df = self._load_companion(symbol)
        if df is None or self._current_timestamp is None:
            return pd.DataFrame()
        cutoff = pd.Timestamp(self._current_timestamp).normalize()
        sub    = df[df.index <= cutoff]
        return sub.iloc[-n:] if not sub.empty else pd.DataFrame()

    def update_bars(self) -> bool:
        """
        Avance d'une barre.
        Tous les symboles primaires passent au même timestamp simultanément —
        aucun risque de désynchronisation.
        """
        if self._cursor >= len(self._dates):
            return False

        ts = self._dates[self._cursor]
        self._cursor += 1
        self._current_timestamp = ts

        # Pas de copie nécessaire — get_latest_bar/get_latest_n_bars slicent _aligned

        self._queue.put(MarketEvent(timestamp=ts, symbols=self._symbols))
        return True

    # -----------------------------------------------------------------------
    # Helpers séries compagnes
    # -----------------------------------------------------------------------

    def _get_companion_bar(self, symbol: str) -> Optional[pd.Series]:
        df = self._load_companion(symbol)
        if df is None or self._current_timestamp is None:
            return None
        cutoff = pd.Timestamp(self._current_timestamp).normalize()
        sub    = df[df.index <= cutoff]
        return sub.iloc[-1] if not sub.empty else None

    def _load_companion(self, symbol: str) -> Optional[pd.DataFrame]:
        """Charge (et met en cache) une série compagne depuis le Parquet.

        La série est réindexée sur le calendrier primaire (intersection des
        symboles tradés) et forward-fillée, de sorte que get_latest_n_bars
        renvoie toujours des barres alignées sur ce même calendrier.
        """
        if symbol not in self._companion_frames:
            try:
                path = self._find_parquet(symbol)
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index).normalize()
                df = df[~df.index.duplicated(keep="last")].sort_index()
                # Align to primary trading calendar to avoid extra off-calendar
                # dates skewing the last-N window (e.g., ADVDEC.NY has more
                # trading days than the primary intersection).
                primary_idx = pd.DatetimeIndex(self._dates)
                df = df.reindex(primary_idx).ffill()
                self._companion_frames[symbol] = df
            except FileNotFoundError:
                self._companion_frames[symbol] = None
        return self._companion_frames[symbol]


# ---------------------------------------------------------------------------
# Handler de secours — lit un CSV brut sans passer par la databank
# ---------------------------------------------------------------------------

class RawCSVHandler(AbstractDataHandler):
    """
    Lit un CSV OHLCV brut directement.
    Utile pour les tests rapides ou les démonstrations.

    Le CSV doit avoir ces colonnes (noms insensibles à la casse) :
    timestamp/date, open, high, low, close, volume
    """

    _COL_ALIASES: dict[str, list[str]] = {
        "timestamp": ["timestamp", "date", "datetime", "time", "Date", "Datetime"],
        "open":      ["open", "Open", "OPEN", "o"],
        "high":      ["high", "High", "HIGH", "h"],
        "low":       ["low", "Low", "LOW", "l"],
        "close":     ["close", "Close", "CLOSE", "c", "adj close", "Adj Close"],
        "volume":    ["volume", "Volume", "VOLUME", "vol", "Vol"],
    }

    def __init__(
        self,
        symbol: str,
        csv_path: Path,
        queue: EventQueue,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> None:
        self._symbol = symbol
        self._queue  = queue
        self._current_timestamp: Optional[datetime] = None

        self._df: pd.DataFrame = self._load_csv(Path(csv_path), start_date, end_date)
        self._cursor: int = 0

    def _load_csv(
        self,
        path: Path,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> pd.DataFrame:
        df = pd.read_csv(path)

        col_map: dict[str, str] = {}
        for standard, aliases in self._COL_ALIASES.items():
            for col in df.columns:
                if col in aliases or col.lower() in [a.lower() for a in aliases]:
                    col_map[col] = standard
                    break

        df = df.rename(columns=col_map)
        missing = [c for c in ["open", "high", "low", "close"] if c not in df.columns]
        if missing:
            raise ValueError(f"RawCSVHandler : colonnes manquantes : {missing}")

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()

        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]

        return df[["open", "high", "low", "close", "volume"] if "volume" in df.columns
                  else ["open", "high", "low", "close"]]

    @property
    def symbol_list(self) -> list[str]:
        return [self._symbol]

    @property
    def current_timestamp(self) -> Optional[datetime]:
        return self._current_timestamp

    def get_latest_bar(self, symbol: str) -> Optional[pd.Series]:
        return self._df.iloc[self._cursor - 1] if self._cursor > 0 else None

    def get_latest_n_bars(self, symbol: str, n: int) -> pd.DataFrame:
        if self._cursor == 0:
            return pd.DataFrame()
        return self._df.iloc[max(0, self._cursor - n): self._cursor]

    def update_bars(self) -> bool:
        if self._cursor >= len(self._df):
            return False
        ts = self._df.index[self._cursor]
        self._cursor += 1
        self._current_timestamp = ts
        self._queue.put(MarketEvent(timestamp=ts, symbols=[self._symbol]))
        return True
