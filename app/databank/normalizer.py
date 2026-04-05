"""
databank/normalizer.py — Conversion CSV/Excel → Parquet normalisé.

Format interne garanti :
    index   : DatetimeIndex (UTC ou naïf), trié ASC, sans doublons
    columns : open  | high | low | close | volume  (volume optionnel)
    dtypes  : float64 pour tout sauf l'index

Toutes les données passent par ce module avant d'être stockées.

Règles de tolérance (données partielles) :
    - Seul 'close' est obligatoire.
    - open  absent → open  = close
    - high  absent → high  = close
    - low   absent → low   = close
    - volume absent → colonne omise (pas de valeur par défaut)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from databank.analyzer import ColumnMapping, _is_excel, _read_raw, detect_frequency


class DataNormalizer:
    """Transforme un DataFrame brut en DataFrame normalisé et le sauvegarde."""

    REQUIRED_COLS = ["close"]                       # seul obligatoire
    OHLC_COLS     = ["open", "high", "low", "close"]
    OPTIONAL_COLS = ["volume"]

    def normalize(
        self,
        df: pd.DataFrame,
        mapping: ColumnMapping,
    ) -> pd.DataFrame:
        """
        Applique le ColumnMapping et retourne un DataFrame normalisé.
        Lève ValueError si 'close' est manquant après mapping.
        """
        # 1. Renommer les colonnes selon le mapping
        rename = {csv_col: std for csv_col, std in mapping.column_map.items() if std}
        df = df.rename(columns=rename)

        # 2. Seul close est requis
        if "close" not in df.columns:
            raise ValueError(
                "Colonne 'close' introuvable après mapping.\n"
                "Vérifiez le mapping — aliases reconnus : close, Close, Price, Value, Last, Settle…"
            )

        # 3. Fallbacks OHLC : si open/high/low absents, on les dérive du close
        if "open"  not in df.columns:
            df["open"]  = df["close"]
        if "high"  not in df.columns:
            df["high"]  = df["close"]
        if "low"   not in df.columns:
            df["low"]   = df["close"]

        # 4. Construire l'index datetime
        if "timestamp" in df.columns:
            fmt = mapping.date_format
            if fmt == "unix":
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", errors="coerce")
            elif fmt == "unix_ms":
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", errors="coerce")
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"], format=fmt,
                                                  errors="coerce")
            df = df.set_index("timestamp")
        elif not isinstance(df.index, pd.DatetimeIndex):
            # Dernière tentative : pandas auto-detect sur l'index
            try:
                df.index = pd.to_datetime(df.index, infer_datetime_format=True,
                                          errors="coerce")
            except Exception:
                raise ValueError(
                    "Aucune colonne timestamp trouvée et l'index n'est pas DatetimeIndex."
                )

        df.index.name = "timestamp"
        df = df.sort_index()

        # 4b. Vérification de la fréquence
        _freq = detect_frequency(df.index)
        if _freq == "intraday":
            raise ValueError(
                "Données intraday non supportées (fréquence sub-journalière détectée).\n"
                "Le moteur fonctionne en mode daily uniquement.\n"
                "Utilisez des données journalières, hebdomadaires ou mensuelles."
            )
        if _freq in ("weekly", "monthly"):
            print(f"  [i]  Frequence detectee : {_freq} -> reechantillonnage journalier (jours ouvres, forward-fill).")
            df = df.resample("B").ffill()

        # 5. Supprimer les doublons de dates (garder le dernier)
        df = df[~df.index.duplicated(keep="last")]

        # 6. Sélectionner uniquement les colonnes nécessaires
        cols = self.OHLC_COLS + [c for c in self.OPTIONAL_COLS if c in df.columns]
        df = df[cols].astype(float)

        # 7. Supprimer les lignes avec NaN sur close
        n_before = len(df)
        df = df.dropna(subset=["close"])
        n_after = len(df)
        if n_before != n_after:
            print(f"  [!]  {n_before - n_after} lignes supprimees (NaN sur close).")

        return df

    def normalize_from_csv(
        self,
        csv_path: Path,
        mapping: ColumnMapping,
    ) -> pd.DataFrame:
        """Lit un CSV ou Excel et normalise selon le mapping."""
        path = Path(csv_path)

        # Récupère les paramètres de lecture depuis le mapping
        encoding = getattr(mapping, "encoding", "utf-8") or "utf-8"
        decimal  = getattr(mapping, "decimal",  ".")     or "."

        df = _read_raw(path, mapping.separator, encoding, decimal)
        return self.normalize(df, mapping)

    def save_parquet(
        self,
        df: pd.DataFrame,
        ticker: str,
        asset_class: str,
        market_data_dir: Path = Path("DATASETS"),
        source_meta: Optional[dict] = None,
    ) -> Path:
        """
        Sauvegarde le DataFrame normalisé en Parquet.

        source_meta : dict optionnel embarqué dans les métadonnées du fichier Parquet
                      (ex: {"provider": "yfinance", "currency": "USD"}).
                      Ces infos sont lisibles sans charger les données via read_parquet_meta().
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        safe_ticker = ticker.replace("^", "_").replace("/", "_")
        out_dir = market_data_dir / asset_class
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{safe_ticker}.parquet"

        table = pa.Table.from_pandas(df)
        if source_meta:
            existing = table.schema.metadata or {}
            extra = {
                (k.encode() if isinstance(k, str) else k):
                (v.encode() if isinstance(v, str) else v)
                for k, v in source_meta.items()
            }
            table = table.replace_schema_metadata({**existing, **extra})
        pq.write_table(table, path, compression="snappy")

        print(f"  OK  Sauvegarde : {path} ({len(df):,} barres)")
        return path

    @staticmethod
    def read_parquet_meta(path: Path) -> dict:
        """
        Lit uniquement les métadonnées custom du fichier Parquet (sans charger les données).
        Retourne un dict str→str, ignore les clés internes pandas/arrow.
        """
        import pyarrow.parquet as pq
        try:
            raw = pq.read_schema(path).metadata or {}
            return {
                k.decode(): v.decode()
                for k, v in raw.items()
                if not k.startswith(b"pandas") and not k.startswith(b"ARROW")
            }
        except Exception:
            return {}

    def load_parquet(
        self,
        ticker: str,
        market_data_dir: Path = Path("DATASETS"),
    ) -> Optional[pd.DataFrame]:
        """Charge un Parquet depuis n'importe quel sous-dossier."""
        safe_ticker = ticker.replace("^", "_").replace("/", "_")
        for subdir in market_data_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("_"):
                path = subdir / f"{safe_ticker}.parquet"
                if path.exists():
                    df = pd.read_parquet(path)
                    df.index = pd.to_datetime(df.index)
                    return df.sort_index()
        return None

    def update_parquet(
        self,
        ticker: str,
        new_df: pd.DataFrame,
        asset_class: str,
        market_data_dir: Path = Path("DATASETS"),
    ) -> Path:
        """
        Fusionne new_df avec les données existantes (évite les doublons).
        Utile pour les mises à jour incrémentales.
        """
        existing = self.load_parquet(ticker, market_data_dir)
        if existing is not None:
            combined = pd.concat([existing, new_df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            print(f"  Fusion : {len(existing):,} existantes + {len(new_df):,} nouvelles"
                  f" = {len(combined):,} barres.")
        else:
            combined = new_df

        return self.save_parquet(combined, ticker, asset_class, market_data_dir)
