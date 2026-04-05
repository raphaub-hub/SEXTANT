"""
databank/analyzer.py — Détection automatique du format d'un fichier CSV ou Excel.

Aucun code à écrire pour importer un nouveau fichier.
Le programme analyse, propose, et tu valides (ou modifies) interactivement.
Le mapping validé est sauvegardé comme profil pour les imports futurs.

Sources supportées (non exhaustif) :
  - TradingView        : time,open,high,low,close,Volume (UNIX timestamps)
  - Yahoo Finance      : Date,Open,High,Low,Close,Adj Close,Volume
  - Stooq              : Date,Open,High,Low,Close,Volume
  - Alpha Vantage      : timestamp,open,high,low,close,volume
  - Investing.com      : Date,Price,Open,High,Low,Vol.
  - FRED               : DATE,VALUE  (single-column series)
  - MetaTrader MT4/5   : <DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<TICKVOL>
  - Bloomberg (CSV)    : Date,Open,High,Low,Close,Volume (après export)
  - Fichiers Excel     : .xlsx / .xls / .xlsm
  - CSV européens      : séparateur ; avec décimales ,
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Structure du mapping
# ---------------------------------------------------------------------------

STANDARD_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

# Encodages à essayer en ordre de priorité
_ENCODINGS = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

# Aliases connus pour chaque colonne standard
_ALIASES: dict[str, list[str]] = {
    "timestamp": [
        "date", "datetime", "time", "timestamp", "ts", "index",
        "Date", "Datetime", "Time", "Timestamp",
        "<DATE>", "<DATETIME>", "<date>",
        "DATE", "DATETIME", "TIME",
        "Gmt time",                        # histdata
    ],
    "open": [
        "open", "Open", "OPEN", "o", "first", "First",
        "<OPEN>", "<open>",
        "Open*",
    ],
    "high": [
        "high", "High", "HIGH", "h", "max", "Max",
        "<HIGH>", "<high>",
        "High*",
    ],
    "low": [
        "low", "Low", "LOW", "l", "min", "Min",
        "<LOW>", "<low>",
        "Low*",
    ],
    "close": [
        "close", "Close", "CLOSE", "c", "last", "Last",
        "adj close", "Adj Close", "adjusted close", "Adjusted Close",
        "close*", "Close*",
        "<CLOSE>", "<close>",
        # Investing.com / macrotrends export the close as "Price"
        "price", "Price", "PRICE",
        # FRED / data providers use "value"
        "value", "Value", "VALUE",
        # Bloomberg / Reuters
        "settle", "Settle", "SETTLE", "settlement", "Settlement",
        # Stooq sometimes uses "Last"
        "last price", "Last Price",
    ],
    "volume": [
        "volume", "Volume", "VOLUME", "vol", "Vol", "VOL",
        "v", "qty", "Qty", "quantity",
        "<VOL>", "<TICKVOL>", "<vol>", "<tickvol>",
        "vol.", "Vol.", "volume*", "Volume*",
        "Total Vol.", "Total Volume",
    ],
}

# Séparateurs à tester
_SEPARATORS = [",", ";", "\t", "|"]


def detect_frequency(dates) -> str:
    """
    Détecte la fréquence dominante d'une série de dates.

    Retourne : 'intraday' | 'daily' | 'weekly' | 'monthly' | 'unknown'

    Seuils (médiane des intervalles en heures) :
      < 22 h  → intraday  (horaire, minute, tick)
      22-60 h → daily     (journalier, incl. gaps week-end)
     60-300 h → weekly    (hebdomadaire ~120-168 h)
      > 300 h → monthly   (mensuel, trimestriel, annuel)
    """
    import pandas as _pd
    if not isinstance(dates, _pd.Series):
        dates = _pd.Series(dates)
    dates = _pd.to_datetime(dates, errors="coerce").dropna().sort_values()
    if len(dates) < 3:
        return "unknown"
    diffs = dates.diff().dropna()
    median_h = diffs.median().total_seconds() / 3600
    if median_h < 22:
        return "intraday"
    elif median_h < 60:
        return "daily"
    elif median_h < 300:
        return "weekly"
    else:
        return "monthly"

# Formats de date à tester (du plus spécifique au moins)
_DATE_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%d.%m.%Y %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y.%m.%d",
    "%Y%m%d",
    "%b %d, %Y",     # Jan 01, 2023
    "%d %b %Y",      # 01 Jan 2023
]

# Extensions de fichiers Excel
_EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}


@dataclass
class ColumnMapping:
    """
    Résultat d'une analyse CSV/Excel.
    csv_col → standard_col (ou None si ignorée).
    """
    csv_path:       Path
    separator:      str
    date_format:    str
    column_map:     dict[str, Optional[str]]   # {csv_col: standard_col ou None}
    decimal:        str  = "."                 # séparateur décimal ("." ou ",")
    encoding:       str  = "utf-8"             # encodage détecté
    ambiguities:    list[str] = field(default_factory=list)
    warnings:       list[str] = field(default_factory=list)
    n_rows:         int = 0
    date_range:     tuple[str, str] = ("", "")
    frequency:      str = "unknown"          # 'daily' | 'weekly' | 'monthly' | 'intraday' | 'unknown'

    def is_valid(self) -> bool:
        """Le mapping est valide si au minimum timestamp + close sont identifiés."""
        mapped = set(self.column_map.values()) - {None}
        return "timestamp" in mapped and "close" in mapped

    def to_profile(self) -> dict:
        return {
            "separator":   self.separator,
            "date_format": self.date_format,
            "decimal":     self.decimal,
            "encoding":    self.encoding,
            "column_map":  self.column_map,
        }


# ---------------------------------------------------------------------------
# Helpers bas niveau
# ---------------------------------------------------------------------------

def _is_excel(path: Path) -> bool:
    return Path(path).suffix.lower() in _EXCEL_EXTENSIONS


def _read_raw(path: Path, sep: str, encoding: str, decimal: str = ".",
              nrows: Optional[int] = None) -> pd.DataFrame:
    """Lit un CSV ou Excel brut sans normalisation."""
    if _is_excel(path):
        return pd.read_excel(path, nrows=nrows, engine="openpyxl")
    kw = dict(sep=sep, encoding=encoding, encoding_errors="replace",
              decimal=decimal, low_memory=False)
    if nrows:
        kw["nrows"] = nrows
    return pd.read_csv(path, **kw)


def _detect_encoding(path: Path) -> str:
    """Essaie plusieurs encodages et retourne le premier qui fonctionne."""
    if _is_excel(path):
        return "utf-8"
    for enc in _ENCODINGS:
        try:
            path.read_text(encoding=enc).encode(enc)
            return enc
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return "latin-1"


# ---------------------------------------------------------------------------
# Analyseur
# ---------------------------------------------------------------------------

class CSVAnalyzer:

    def analyze(self, csv_path: Path) -> ColumnMapping:
        """Analyse un fichier CSV/Excel et retourne un ColumnMapping proposé."""
        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable : {csv_path}")

        is_excel = _is_excel(path)
        encoding = _detect_encoding(path) if not is_excel else "utf-8"

        sep     = self._detect_separator(path, encoding) if not is_excel else ","
        decimal = self._detect_decimal(path, sep, encoding) if not is_excel else "."

        df          = _read_raw(path, sep, encoding, decimal, nrows=1000)
        col_map, ambiguities = self._map_columns(list(df.columns))
        date_fmt, date_range, n_rows, frequency = self._detect_date_info(path, sep, encoding, decimal, col_map)

        warnings = []
        if "close" not in set(col_map.values()):
            warnings.append(
                "Aucune colonne 'close' identifiée — vérifiez le mapping.\n"
                "Sources connues : Price (Investing.com), Value (FRED), Last, Settle…"
            )

        return ColumnMapping(
            csv_path=path,
            separator=sep,
            date_format=date_fmt,
            decimal=decimal,
            encoding=encoding,
            column_map=col_map,
            ambiguities=ambiguities,
            warnings=warnings,
            n_rows=n_rows,
            date_range=date_range,
            frequency=frequency,
        )

    def _detect_separator(self, path: Path, encoding: str) -> str:
        try:
            sample = path.read_text(encoding=encoding, errors="replace")[:4096]
        except Exception:
            sample = path.read_text(encoding="latin-1", errors="replace")[:4096]
        first_line = sample.split("\n")[0]
        counts = {sep: first_line.count(sep) for sep in _SEPARATORS}
        return max(counts, key=counts.get)

    def _detect_decimal(self, path: Path, sep: str, encoding: str) -> str:
        """
        Détecte si les nombres utilisent ',' comme décimale (format européen).
        Typique avec séparateur ';' : 1.234,56 → decimal=','
        """
        if sep != ";":
            return "."
        try:
            sample = path.read_text(encoding=encoding, errors="replace")
            # Cherche un pattern nombre avec virgule décimale : ex "1234,56" ou "0,5"
            import re
            # Trouve les cellules qui ressemblent à des nombres avec virgule
            cells = re.findall(r"[;\n](-?\d+,\d+)(?:[;\n]|$)", sample[:8192])
            if cells:
                return ","
        except Exception:
            pass
        return "."

    def _map_columns(
        self,
        columns: list[str],
    ) -> tuple[dict[str, Optional[str]], list[str]]:
        """
        Associe chaque colonne CSV à une colonne standard.
        Retourne (mapping, liste des ambiguités détectées).
        """
        mapping: dict[str, Optional[str]] = {col: None for col in columns}
        used_standards: dict[str, str] = {}
        ambiguities: list[str] = []

        for csv_col in columns:
            col_stripped = csv_col.strip()
            for standard, aliases in _ALIASES.items():
                if (col_stripped in aliases
                        or col_stripped.lower() in [a.lower() for a in aliases]):
                    if standard in used_standards:
                        ambiguities.append(
                            f"'{csv_col}' et '{used_standards[standard]}' "
                            f"semblent toutes deux être '{standard}' — "
                            f"'{used_standards[standard]}' conservée, '{csv_col}' ignorée."
                        )
                    else:
                        mapping[csv_col] = standard
                        used_standards[standard] = csv_col
                    break

        return mapping, ambiguities

    def _detect_date_info(
        self,
        path: Path,
        sep: str,
        encoding: str,
        decimal: str,
        col_map: dict[str, Optional[str]],
    ) -> tuple[str, tuple[str, str], int, str]:
        """
        Détecte le format de date, la plage temporelle et la fréquence.
        Retourne (fmt, date_range, n_rows, frequency).
        """
        date_col = next((c for c, s in col_map.items() if s == "timestamp"), None)
        if date_col is None:
            return ("%Y-%m-%d", ("?", "?"), 0, "unknown")

        try:
            df_full = _read_raw(path, sep, encoding, decimal)
        except Exception:
            return ("%Y-%m-%d", ("?", "?"), 0, "unknown")

        n_rows = len(df_full)
        if date_col not in df_full.columns:
            return ("%Y-%m-%d", ("?", "?"), n_rows, "unknown")

        sample = str(df_full[date_col].iloc[0]).strip()

        # UNIX timestamp (secondes) : entier > 86400
        if sample.isdigit() and int(sample) > 86400 and len(sample) <= 10:
            dates = pd.Series(dtype="datetime64[ns]")
            try:
                dates = pd.to_datetime(df_full[date_col], unit="s", errors="coerce")
                date_range = (str(dates.min().date()), str(dates.max().date()))
            except Exception:
                date_range = ("?", "?")
            return "unix", date_range, n_rows, detect_frequency(dates)

        # UNIX timestamp (millisecondes) : 13 chiffres
        if sample.isdigit() and len(sample) >= 13:
            dates = pd.Series(dtype="datetime64[ns]")
            try:
                dates = pd.to_datetime(df_full[date_col], unit="ms", errors="coerce")
                date_range = (str(dates.min().date()), str(dates.max().date()))
            except Exception:
                date_range = ("?", "?")
            return "unix_ms", date_range, n_rows, detect_frequency(dates)

        # Formats string
        fmt = "%Y-%m-%d"
        for candidate in _DATE_FORMATS:
            try:
                pd.to_datetime(sample, format=candidate)
                fmt = candidate
                break
            except (ValueError, TypeError):
                continue

        dates = pd.Series(dtype="datetime64[ns]")
        try:
            dates = pd.to_datetime(df_full[date_col], format=fmt, errors="coerce")
            date_range = (str(dates.min().date()), str(dates.max().date()))
        except Exception:
            date_range = ("?", "?")

        return fmt, date_range, n_rows, detect_frequency(dates)


# ---------------------------------------------------------------------------
# Affichage interactif
# ---------------------------------------------------------------------------

def display_mapping(mapping: ColumnMapping) -> None:
    """Affiche le mapping proposé dans la console."""
    sep_display = {
        ",": "virgule", ";": "point-virgule", "\t": "tabulation", "|": "pipe"
    }.get(mapping.separator, mapping.separator)

    ext = Path(mapping.csv_path).suffix.lower() if mapping.csv_path else ""
    fmt = "Excel" if ext in _EXCEL_EXTENSIONS else "CSV"

    print(f"\n{'-' * 60}")
    print(f"  Analyse de : {Path(mapping.csv_path).name}  [{fmt}]")
    print(f"  Lignes : {mapping.n_rows:,} | Séparateur : {sep_display} | "
          f"Décimale : '{mapping.decimal}' | Encodage : {mapping.encoding}")
    print(f"{'-' * 60}")
    print(f"  {'Colonne CSV':<22} {'-> Standard':<16} Etat")
    print(f"  {'-'*22} {'-'*16} {'-'*12}")

    for csv_col, standard in mapping.column_map.items():
        state = "OK" if standard is not None else "ignorée"
        print(f"  {csv_col:<22} {(standard or '—'):<16} {state}")

    print(f"{'-' * 60}")

    if mapping.ambiguities:
        print("  !  Ambiguités détectées :")
        for a in mapping.ambiguities:
            print(f"     • {a}")

    if mapping.warnings:
        print("  ⚠  Avertissements :")
        for w in mapping.warnings:
            print(f"     • {w}")

    if mapping.date_range[0] != "?":
        print(f"\n  [DATE] Format : {mapping.date_format}")
        print(f"     Plage : {mapping.date_range[0]}  →  {mapping.date_range[1]}")

    print()


def interactive_edit(mapping: ColumnMapping) -> ColumnMapping:
    """Permet à l'utilisateur de modifier le mapping interactivement."""
    print("  Modifier le mapping (entrée vide = conserver la valeur actuelle) :")
    print(f"  Valeurs possibles : {', '.join(STANDARD_COLUMNS)}, ignorer\n")

    new_map = dict(mapping.column_map)

    for csv_col, current_standard in list(mapping.column_map.items()):
        current_display = current_standard or "ignorée"
        user_input = input(
            f"  '{csv_col}' → actuellement [{current_display}] : "
        ).strip().lower()

        if not user_input:
            continue
        if user_input in ("ignorer", "ignore"):
            new_map[csv_col] = None
        elif user_input in STANDARD_COLUMNS:
            existing = next((c for c, s in new_map.items() if s == user_input), None)
            if existing and existing != csv_col:
                print(f"  !  '{user_input}' déjà assigné à '{existing}'. Désassignation.")
                new_map[existing] = None
            new_map[csv_col] = user_input
        else:
            print(f"  Valeur inconnue '{user_input}' — ignorée.")

    return ColumnMapping(
        csv_path=mapping.csv_path,
        separator=mapping.separator,
        date_format=mapping.date_format,
        decimal=mapping.decimal,
        encoding=mapping.encoding,
        column_map=new_map,
        ambiguities=[],
        warnings=mapping.warnings,
        n_rows=mapping.n_rows,
        date_range=mapping.date_range,
    )


# ---------------------------------------------------------------------------
# Profils sauvegardés
# ---------------------------------------------------------------------------

PROFILES_DIR = Path("DATASETS/_profiles")


def save_profile(name: str, mapping: ColumnMapping) -> Path:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = PROFILES_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping.to_profile(), f, indent=2, ensure_ascii=False)
    print(f"  Profil sauvegardé : {path}")
    return path


def load_profile(name: str) -> Optional[dict]:
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return [p.stem for p in PROFILES_DIR.glob("*.json")
            if p.stem not in ("catalog", "derived")]
