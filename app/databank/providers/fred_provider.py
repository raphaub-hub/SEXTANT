"""
databank/providers/fred_provider.py — Import depuis FRED / ALFRED.

FRED  (Federal Reserve Economic Data) : derniere revision de chaque serie.
ALFRED (Archival FRED)                : premiere date de publication reelle.

Cle API gratuite : https://fred.stlouisfed.org/docs/api/api_key.html

Modes
-----
"first"  : ALFRED — index = realtime_start (date ou la valeur est devenue
           publiquement disponible). Elimine tout look-ahead bias.
"latest" : FRED   — index = date de reference (ex: 2024-01-01 pour jan. 2024).
           Utilise la derniere revision connue de chaque observation.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

import pandas as pd

FRED_BASE_URL = "https://api.stlouisfed.org/fred"


class FREDProvider:

    # ------------------------------------------------------------------ fetch

    def fetch(
        self,
        series_id: str,
        mode: str = "first",
        api_key: str = "",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        units: str = "lin",
    ) -> pd.DataFrame:
        """
        Telecharge une serie FRED et retourne un DataFrame OHLC normalise.

        Parameters
        ----------
        series_id  : identifiant FRED (ex: "CPIAUCSL", "UNRATE", "GDP")
        mode       : "first" (ALFRED, premiere publication) ou
                     "latest" (FRED standard, derniere revision)
        api_key    : cle API FRED
        start_date : date de debut au format "YYYY-MM-DD" (optionnel)
        end_date   : date de fin   au format "YYYY-MM-DD" (optionnel)
        units      : transformation FRED appliquee cote serveur
                     "lin" = niveau brut (defaut)
                     "pc1" = % change year-over-year
                     "pch" = % change period-over-period
                     "ch1" = variation absolue year-over-year
                     "chg" = variation absolue period-over-period
                     "log" = logarithme naturel

        Returns
        -------
        DataFrame avec DatetimeIndex et colonnes open/high/low/close.
        Les donnees mensuelles/hebdo seront resamplees en daily par le
        normalizer avant sauvegarde.
        """
        if mode == "first":
            return self._fetch_alfred(series_id, api_key, start_date, end_date, units)
        else:
            return self._fetch_fred_latest(series_id, api_key, start_date, end_date, units)

    def _fetch_alfred(
        self,
        series_id: str,
        api_key: str,
        start: Optional[str],
        end: Optional[str],
        units: str = "lin",
    ) -> pd.DataFrame:
        """
        Mode ALFRED : pour chaque date d'observation, recupere la valeur
        telle qu'elle etait lors de sa PREMIERE publication.
        L'index du DataFrame est realtime_start (date reelle de disponibilite).
        """
        # ALFRED n'accepte pas les transformations serveur (units != lin) quand
        # realtime_start != realtime_end → on recupere toujours le niveau brut
        # et on applique la transformation cote client.
        params: dict = {
            "series_id":      series_id,
            "api_key":        api_key,
            "file_type":      "json",
            "realtime_start": "1776-07-04",   # toutes les vintages
            "realtime_end":   "9999-12-31",
            # units intentionnellement absent : FRED refuse la combinaison
            # realtime_start=all + units!=lin (erreur 400)
        }
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        data = self._get(f"{FRED_BASE_URL}/series/observations", params)
        observations = data.get("observations", [])
        if not observations:
            raise ValueError(f"Aucune donnee retournee pour la serie '{series_id}'.")

        rows = []
        for obs in observations:
            if obs.get("value") in (".", "", None):
                continue
            try:
                rows.append({
                    "obs_date":       obs["date"],
                    "realtime_start": obs["realtime_start"],
                    "value":          float(obs["value"]),
                })
            except (ValueError, KeyError):
                continue

        if not rows:
            raise ValueError(f"Aucune observation valide pour '{series_id}'.")

        df = pd.DataFrame(rows)
        df["obs_date"]       = pd.to_datetime(df["obs_date"])
        df["realtime_start"] = pd.to_datetime(df["realtime_start"])

        # Pour chaque date d'observation : garder uniquement la PREMIERE publication
        df = (
            df.sort_values("realtime_start")
              .groupby("obs_date", as_index=False)
              .first()
        )

        # Transformation client-side (pc1 / pch / ch1 / chg)
        if units and units != "lin":
            # Trier par date d'observation pour calculer les ecarts temporels corrects
            df = df.sort_values("obs_date").reset_index(drop=True)
            vals = df["value"]

            # Nombre de periodes pour le YoY : 12 pour mensuel, 52 pour hebdo, 4 pour trimestriel
            if len(df) > 1:
                _med_days = df["obs_date"].diff().median().days
            else:
                _med_days = 30
            _yoy_n = max(1, round(365.0 / max(_med_days, 1)))

            if units == "pc1":       # % change year-over-year
                df["value"] = (vals / vals.shift(_yoy_n) - 1) * 100
            elif units == "pch":     # % change period-over-period
                df["value"] = (vals / vals.shift(1) - 1) * 100
            elif units == "ch1":     # absolute change year-over-year
                df["value"] = vals - vals.shift(_yoy_n)
            elif units == "chg":     # absolute change period-over-period
                df["value"] = vals - vals.shift(1)

            # Supprimer les lignes NaN creees par le shift (debut de serie)
            df = df.dropna(subset=["value"])

        # Index = date de publication reelle
        df = df.set_index("realtime_start").sort_index()
        df.index.name = "timestamp"

        # Supprimer les doublons eventuels sur l'index
        df = df[~df.index.duplicated(keep="last")]

        df = df.rename(columns={"value": "close"})
        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"]  = df["close"]

        return df[["open", "high", "low", "close"]]

    def _fetch_fred_latest(
        self,
        series_id: str,
        api_key: str,
        start: Optional[str],
        end: Optional[str],
        units: str = "lin",
    ) -> pd.DataFrame:
        """
        Mode FRED standard : derniere revision connue de chaque observation.
        L'index est la date de reference de la donnee (ex: 2024-01-01 pour jan).
        """
        params: dict = {
            "series_id": series_id,
            "api_key":   api_key,
            "file_type": "json",
        }
        if units and units != "lin":
            params["units"] = units
        if start:
            params["observation_start"] = start
        if end:
            params["observation_end"] = end

        data = self._get(f"{FRED_BASE_URL}/series/observations", params)
        observations = data.get("observations", [])
        if not observations:
            raise ValueError(f"Aucune donnee retournee pour la serie '{series_id}'.")

        rows = []
        for obs in observations:
            if obs.get("value") in (".", "", None):
                continue
            try:
                rows.append({
                    "timestamp": obs["date"],
                    "close":     float(obs["value"]),
                })
            except (ValueError, KeyError):
                continue

        if not rows:
            raise ValueError(f"Aucune observation valide pour '{series_id}'.")

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]

        df["open"] = df["close"]
        df["high"] = df["close"]
        df["low"]  = df["close"]

        return df[["open", "high", "low", "close"]]

    # ----------------------------------------------------------- series info

    def get_series_info(self, series_id: str, api_key: str) -> dict:
        """
        Retourne les metadonnees d'une serie FRED :
        titre, frequence, unite, date de debut/fin, source...
        """
        params = {
            "series_id": series_id,
            "api_key":   api_key,
            "file_type": "json",
        }
        data = self._get(f"{FRED_BASE_URL}/series", params)
        seriess = data.get("seriess", [])
        if not seriess:
            raise ValueError(f"Serie '{series_id}' introuvable sur FRED.")
        return seriess[0]

    # --------------------------------------------------------------- helpers

    def _get(self, url: str, params: dict) -> dict:
        query    = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"
        try:
            with urllib.request.urlopen(full_url, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            # Masquer la cle API dans les messages d'erreur
            api_key = params.get("api_key", "")
            if api_key:
                body = body.replace(api_key, "***")
            raise ValueError(f"FRED API erreur {e.code}: {body}")
        except Exception as e:
            raise ValueError(f"Erreur reseau : {e}")
