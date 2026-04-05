"""
databank/catalog.py — Registre des assets disponibles dans la databank.

Le catalog.json répertorie tout ce qui est disponible localement :
ticker, nom, classe, devise, source, plage de dates.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


CATALOG_PATH = Path("DATASETS/_profiles/catalog.json")

ASSET_CLASSES = ["equity", "index", "fx", "crypto", "indicator", "other"]


def _load() -> dict[str, dict]:
    if CATALOG_PATH.exists():
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(catalog: dict[str, dict]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


def register(
    ticker: str,
    name: str,
    asset_class: str,
    currency: str,
    provider: str,
    df: Any,
) -> None:
    """Ajoute ou met à jour une entrée dans le catalog."""
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"Classe d'actif invalide : '{asset_class}'. Valides : {ASSET_CLASSES}")

    catalog = _load()
    catalog[ticker] = {
        "ticker":     ticker,
        "name":       name,
        "class":      asset_class,
        "currency":   currency,
        "provider":   provider,
        "n_bars":     len(df),
        "start":      str(df.index.min().date()),
        "end":        str(df.index.max().date()),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(catalog)


def get(ticker: str) -> Optional[dict]:
    return _load().get(ticker)


def reclassify(ticker: str, new_class: str) -> bool:
    """Met à jour la classe d'un asset dans le catalog (sans toucher au fichier Parquet)."""
    if new_class not in ASSET_CLASSES:
        raise ValueError(f"Classe invalide : '{new_class}'. Valides : {ASSET_CLASSES}")
    catalog = _load()
    if ticker not in catalog:
        return False
    catalog[ticker]["class"] = new_class
    _save(catalog)
    return True


def delete(ticker: str) -> Optional[Path]:
    """
    Supprime un asset du catalogue et retourne le chemin du fichier Parquet
    (pour que l'appelant puisse le supprimer s'il le souhaite).
    """
    catalog = _load()
    if ticker not in catalog:
        return None
    del catalog[ticker]
    _save(catalog)
    # Chercher le parquet dans tous les sous-dossiers
    market_data = Path("DATASETS")
    safe = ticker.replace("^", "_").replace("/", "_")
    for subdir in sorted(market_data.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("_"):
            for candidate in [f"{safe}.parquet", f"{ticker}.parquet"]:
                p = subdir / candidate
                if p.exists():
                    return p
    return None


def list_assets(asset_class: Optional[str] = None) -> list[dict]:
    catalog = _load()
    entries = list(catalog.values())
    if asset_class:
        entries = [e for e in entries if e["class"] == asset_class]
    return sorted(entries, key=lambda x: (x["class"], x["ticker"]))


def print_catalog(asset_class: Optional[str] = None) -> None:
    entries = list_assets(asset_class)
    if not entries:
        print("  Databank vide. Utilisez : python -m databank.updater import ...")
        return

    print(f"\n  {'Ticker':<14} {'Classe':<10} {'Devise':<6} {'Barres':>8}  {'Début':<12} {'Fin':<12}  Nom")
    print(f"  {'-'*14} {'-'*10} {'-'*6} {'-'*8}  {'-'*12} {'-'*12}  {'-'*20}")

    for e in entries:
        print(
            f"  {e['ticker']:<14} {e['class']:<10} {e['currency']:<6} "
            f"{e['n_bars']:>8,}  {e['start']:<12} {e['end']:<12}  {e.get('name', '')}"
        )
    print()
