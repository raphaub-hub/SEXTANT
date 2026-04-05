"""
databank/fred_config.py — Gestion de la cle API FRED locale.

La cle est stockee dans DATASETS/_profiles/fred_config.json (jamais dans le code).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path("DATASETS/_profiles/fred_config.json")


def get_api_key() -> Optional[str]:
    """Retourne la cle API FRED enregistree, ou None si absente."""
    if not _CONFIG_PATH.exists():
        return None
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f).get("api_key") or None
    except Exception:
        return None


def set_api_key(key: str) -> None:
    """Sauvegarde la cle API FRED localement."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _CONFIG_PATH.exists():
        try:
            with open(_CONFIG_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data["api_key"] = key.strip()
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def is_configured() -> bool:
    """True si une cle API valide est enregistree."""
    key = get_api_key()
    return bool(key and len(key) > 10)
