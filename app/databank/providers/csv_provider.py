"""
databank/providers/csv_provider.py — Import depuis un fichier CSV local.

Utilise CSVAnalyzer pour détecter automatiquement le format,
propose le mapping à l'utilisateur, puis normalise les données.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from databank.analyzer import (
    CSVAnalyzer,
    ColumnMapping,
    display_mapping,
    interactive_edit,
    load_profile,
    save_profile,
)
from databank.normalizer import DataNormalizer
from databank.providers.base import AbstractProvider


class CSVProvider(AbstractProvider):

    @property
    def name(self) -> str:
        return "csv"

    def fetch(
        self,
        ticker: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "CSVProvider.fetch() n'est pas disponible directement. "
            "Utilisez CSVProvider.import_file() à la place."
        )

    def import_file(
        self,
        csv_path: Path,
        profile_name: Optional[str] = None,
        interactive: bool = True,
    ) -> tuple[pd.DataFrame, ColumnMapping]:
        """
        Importe un fichier CSV avec détection automatique du format.

        Args:
            csv_path:     Chemin vers le fichier CSV.
            profile_name: Nom d'un profil sauvegardé à utiliser (skip la détection).
            interactive:  Si True, permet la modification manuelle du mapping.

        Returns:
            (DataFrame normalisé, ColumnMapping utilisé)
        """
        analyzer   = CSVAnalyzer()
        normalizer = DataNormalizer()
        csv_path   = Path(csv_path)

        # 1. Charger ou détecter le mapping
        mapping = analyzer.analyze(csv_path)

        # 2. Tenter de charger un profil existant
        if profile_name:
            profile = load_profile(profile_name)
            if profile:
                print(f"  Profil '{profile_name}' chargé.")
                mapping.separator   = profile["separator"]
                mapping.date_format = profile["date_format"]
                mapping.column_map  = profile["column_map"]
            else:
                print(f"  Profil '{profile_name}' introuvable — détection automatique.")

        # 3. Afficher le mapping proposé
        display_mapping(mapping)

        if not mapping.is_valid():
            print("  ❌ Mapping invalide — correction requise.")
            if not interactive:
                raise ValueError("Mapping auto-détecté invalide. Vérifiez le format du fichier.")
            interactive = True

        # 4. Permettre la modification
        if interactive:
            answer = input("  Accepter ce mapping ? [O/n/modifier] : ").strip().lower()
            if answer in ("n", "non", "no"):
                print("  Import annulé.")
                raise ValueError("Import CSV annulé par l'utilisateur.")
            elif answer in ("m", "modifier", "edit", "e"):
                mapping = interactive_edit(mapping)
                display_mapping(mapping)
                if not mapping.is_valid():
                    raise ValueError("Mapping toujours invalide après modification.")

        # 5. Proposer de sauvegarder le profil
        if interactive and profile_name is None:
            save_ans = input("  Sauvegarder ce mapping comme profil ? [nom / entrée=non] : ").strip()
            if save_ans:
                save_profile(save_ans, mapping)

        # 6. Normaliser
        df = normalizer.normalize_from_csv(csv_path, mapping)
        return df, mapping
