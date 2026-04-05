"""
databank/derived.py — Séries dérivées (ratios, différences, combinaisons).

Une série dérivée est calculée à partir de séries brutes déjà dans la databank.
Elle est stockée comme n'importe quelle autre série (Parquet) et mise à jour
automatiquement quand ses composants changent.

Formules supportées (syntaxe simple, pas d'eval arbitraire) :
  A - B
  A + B
  A * B
  A / B
  A / (B + C)
  (A - B) / (A + B)
  A / (B + C + D)

Les noms de variables correspondent aux tickers dans la databank.
Insensibles à la casse.

Exemples :
  NVLF       = "UVOL - DVOL"
  UVOL_PCT   = "UVOL / (UVOL + DVOL)"
  VIX3M_VIX  = "VIX3M / VIX"
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from databank.normalizer import DataNormalizer

DERIVED_DEFS_PATH = Path("DATASETS/_profiles/derived.json")
MARKET_DATA_DIR   = Path("DATASETS")
DERIVED_CLASS     = "indicator"


# ---------------------------------------------------------------------------
# Parsing de formules
# ---------------------------------------------------------------------------

def _extract_tickers(formula: str) -> list[str]:
    """Extrait les noms de tickers d'une formule (tokens alphabétiques+_)."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\.]*", formula)
    return list(dict.fromkeys(tokens))  # dédupliqué, ordre préservé


def _safe_eval(formula: str, series_map: dict[str, pd.Series]) -> pd.Series:
    """
    Évalue une formule arithmétique simple sur des pd.Series.
    Seules les opérations +, -, *, / et les parenthèses sont autorisées.
    Aucun accès à des fonctions Python arbitraires.
    """
    # Validation de la formule : uniquement caractères autorisés
    allowed = re.compile(r"^[A-Za-z0-9_\.\s\+\-\*\/\(\)]+$")
    if not allowed.match(formula):
        raise ValueError(
            f"Formule invalide : '{formula}'\n"
            f"Seuls +, -, *, /, parenthèses et noms de tickers sont autorisés."
        )

    # Construire les locals avec les séries alignées
    local_vars = {name.upper(): series for name, series in series_map.items()}

    # Remplacer les noms de tickers dans la formule par leurs versions uppercase
    formula_upper = re.sub(
        r"[A-Za-z][A-Za-z0-9_\.]*",
        lambda m: m.group(0).upper(),
        formula,
    )

    try:
        result = eval(formula_upper, {"__builtins__": {}}, local_vars)  # noqa: S307
    except Exception as e:
        raise ValueError(f"Erreur de calcul pour '{formula}' : {e}") from e

    if not isinstance(result, pd.Series):
        raise ValueError(f"La formule '{formula}' ne retourne pas une série.")

    return result


# ---------------------------------------------------------------------------
# Gestionnaire des dérivées
# ---------------------------------------------------------------------------

class DerivedSeriesManager:

    def __init__(
        self,
        market_data_dir: Path = MARKET_DATA_DIR,
        defs_path: Path = DERIVED_DEFS_PATH,
    ) -> None:
        self._market_data_dir = Path(market_data_dir)
        self._defs_path       = Path(defs_path)
        self._normalizer      = DataNormalizer()

    # -----------------------------------------------------------------------
    # Gestion des définitions
    # -----------------------------------------------------------------------

    def _load_defs(self) -> dict[str, dict]:
        if self._defs_path.exists():
            with open(self._defs_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_defs(self, defs: dict[str, dict]) -> None:
        self._defs_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._defs_path, "w", encoding="utf-8") as f:
            json.dump(defs, f, indent=2, ensure_ascii=False)

    def add(
        self,
        name: str,
        formula: str,
        unit: str = "Other",
        currency: str = "",          # alias kept for backward compat
        description: str = "",
    ) -> None:
        """
        Déclare une nouvelle série dérivée.
        N'effectue pas encore le calcul — utiliser compute() pour ça.
        """
        name    = name.upper()
        tickers = _extract_tickers(formula)
        # unit prend la priorité ; currency est l'ancien nom (rétro-compat)
        stored_unit = unit if unit != "Other" or not currency else currency

        defs = self._load_defs()
        defs[name] = {
            "name":        name,
            "formula":     formula,
            "components":  tickers,
            "currency":    stored_unit,
            "description": description,
        }
        self._save_defs(defs)
        print(f"  Dérivée '{name}' définie : {formula}")
        print(f"  Composants requis : {tickers}")
        print(f"  Lance 'python -m databank.updater derived compute' pour calculer.")

    def remove(self, name: str) -> None:
        defs = self._load_defs()
        name = name.upper()
        if name not in defs:
            print(f"  '{name}' introuvable dans les dérivées.")
            return
        del defs[name]
        self._save_defs(defs)
        print(f"  Dérivée '{name}' supprimée.")

    def list(self) -> list[dict]:
        return list(self._load_defs().values())

    def print_list(self) -> None:
        defs = self._load_defs()
        if not defs:
            print("  Aucune série dérivée définie.")
            print("  Exemple : python -m databank.updater derived add --name NVLF --formula \"UVOL - DVOL\"")
            return

        print(f"\n  {'Nom':<18} {'Formule':<35} {'Composants'}")
        print(f"  {'-'*18} {'-'*35} {'-'*30}")
        for d in defs.values():
            components = ", ".join(d["components"])
            print(f"  {d['name']:<18} {d['formula']:<35} {components}")
        print()

    # -----------------------------------------------------------------------
    # Calcul
    # -----------------------------------------------------------------------

    def compute(
        self,
        name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> None:
        """
        Calcule et sauvegarde une dérivée (ou toutes si name=None).
        Les composants doivent déjà être dans la databank.
        """
        from databank import catalog as cat

        defs = self._load_defs()
        if not defs:
            print("  Aucune série dérivée définie.")
            return

        targets = {name.upper(): defs[name.upper()]} if name else defs

        for derived_name, defn in targets.items():
            # Ne pas écraser une série déjà présente avec provider != "derived"
            existing = self._normalizer.load_parquet(derived_name, self._market_data_dir)
            from databank.catalog import get as cat_get
            entry = cat_get(derived_name)
            if existing is not None and entry and entry.get("provider") not in (None, "derived"):
                print(f"\n  '{derived_name}' ignoré — données directes présentes (provider: {entry['provider']})")
                continue
            print(f"\n  Calcul de {derived_name} = {defn['formula']}")
            self._compute_one(derived_name, defn, start_date, end_date)

    def _compute_one(
        self,
        name: str,
        defn: dict,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> None:
        from databank import catalog as cat

        # 1. Charger les composants
        series_map: dict[str, pd.Series] = {}
        missing = []

        for ticker in defn["components"]:
            df = self._normalizer.load_parquet(ticker, self._market_data_dir)
            if df is None:
                missing.append(ticker)
            else:
                series_map[ticker.upper()] = df["close"]

        if missing:
            print(f"  ERREUR : composants manquants dans la databank : {missing}")
            print(f"  Importez-les d'abord avec 'python -m databank.updater import'")
            return

        # 2. Normaliser les index en date pure (daily data — supprime les heures)
        #    Nécessaire car TradingView exporte des timestamps intraday qui diffèrent
        #    légèrement selon les séries (ex: VIX à 09:30, VIX3M à 16:00 le même jour).
        normalized = {}
        for key, series in series_map.items():
            s = series.copy()
            s.index = pd.to_datetime(s.index).normalize()  # garde uniquement la date
            s = s[~s.index.duplicated(keep="last")]
            normalized[key] = s

        # 3. Aligner les séries sur un index commun (inner join)
        combined = pd.concat(normalized, axis=1).dropna()
        combined.columns = list(normalized.keys())

        if start_date:
            combined = combined[combined.index >= pd.Timestamp(start_date)]
        if end_date:
            combined = combined[combined.index <= pd.Timestamp(end_date)]

        if combined.empty:
            print(f"  ERREUR : aucune donnée commune entre les composants.")
            return

        # 3. Évaluer la formule
        aligned_map = {col: combined[col] for col in combined.columns}
        try:
            result = _safe_eval(defn["formula"], aligned_map)
        except ValueError as e:
            print(f"  ERREUR : {e}")
            return

        # 4. Construire le DataFrame normalisé
        result_df = pd.DataFrame({
            "open":   result,
            "high":   result,
            "low":    result,
            "close":  result,
            "volume": 0.0,
        })
        result_df.index.name = "timestamp"
        result_df = result_df.dropna(subset=["close"])

        # 5. Sauvegarder avec métadonnées de provenance
        _components = ", ".join(defn.get("components", []))
        path = self._normalizer.save_parquet(
            result_df, name, DERIVED_CLASS, self._market_data_dir,
            source_meta={
                "provider":    "derived",
                "formula":     defn.get("formula", ""),
                "components":  _components,
                "currency":    defn.get("currency", ""),
                "asset_class": DERIVED_CLASS,
                "ticker":      name,
            },
        )

        # 6. Enregistrer dans le catalog
        cat.register(
            ticker=name,
            name=defn.get("description") or f"{defn['formula']}",
            asset_class=DERIVED_CLASS,
            currency=defn.get("currency", "USD"),
            provider="derived",
            df=result_df,
        )
        print(f"  OK '{name}' calculé sur {len(result_df):,} barres.")


# ---------------------------------------------------------------------------
# Dérivées standard — pré-définies pour la databank breadth
# ---------------------------------------------------------------------------

STANDARD_DERIVED: list[dict] = [
    # NYSE volume breadth
    {
        "name":        "UVOL_PCT",
        "formula":     "UVOL / (UVOL + DVOL)",
        "currency":    "% (rate / yield)",
        "description": "NYSE Upside Volume % of Total",
    },
    # VIX term structure ratios
    {
        "name":        "VIX3M_VIX",
        "formula":     "VIX3M / VIX",
        "currency":    "Index value",
        "description": "VIX Term Structure: 3-Month / 1-Month",
    },
    {
        "name":        "VIX_VIX9D",
        "formula":     "VIX / VIX9D",
        "currency":    "Index value",
        "description": "VIX Term Structure: 1-Month / 9-Day",
    },
]


def register_standard_derived() -> None:
    """
    Enregistre toutes les dérivées standard dans derived.json.
    Appelé une seule fois lors de l'initialisation de la databank breadth.
    """
    manager = DerivedSeriesManager()
    defs    = manager._load_defs()
    added   = 0

    for d in STANDARD_DERIVED:
        if d["name"] not in defs:
            defs[d["name"]] = {
                "name":        d["name"],
                "formula":     d["formula"],
                "components":  _extract_tickers(d["formula"]),
                "currency":    d.get("currency", "USD"),
                "description": d.get("description", ""),
            }
            added += 1

    manager._save_defs(defs)
    if added:
        print(f"  {added} dérivées standard enregistrées.")
    else:
        print(f"  Toutes les dérivées standard sont déjà enregistrées.")
