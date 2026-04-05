"""
databank/updater.py — CLI de gestion de la databank.

Commandes disponibles :

  python -m databank.updater list
      → Affiche tous les assets disponibles

  python -m databank.updater import --file data.csv
      → Import interactif d'un CSV (détection automatique du format)

  python -m databank.updater import --file data.csv --profile yahoo_finance
      → Import avec un profil de mapping sauvegardé

  python -m databank.updater download --ticker ^GSPC --from 2010-01-01
      → Télécharge le S&P500 depuis Yahoo Finance

  python -m databank.updater update --ticker AAPL
      → Met à jour jusqu'à aujourd'hui

  python -m databank.updater inspect --file data.csv
      → Analyse un CSV sans l'importer

  python -m databank.updater profiles
      → Liste les profils de mapping sauvegardés
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Force UTF-8 sur les terminaux Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MARKET_DATA_DIR = Path("DATASETS")


def cmd_list(args) -> None:
    from databank.catalog import print_catalog
    cls = getattr(args, "class", None)
    print_catalog(cls)


def cmd_import(args) -> None:
    from databank.providers.csv_provider import CSVProvider
    from databank.normalizer import DataNormalizer
    from databank import catalog

    provider    = CSVProvider()
    normalizer  = DataNormalizer()
    csv_path    = Path(args.file)
    interactive = not getattr(args, "non_interactive", False)

    df, mapping = provider.import_file(
        csv_path=csv_path,
        profile_name=getattr(args, "profile", None),
        interactive=interactive,
    )

    # Demander les métadonnées si non fournies
    ticker = getattr(args, "ticker", None) or input("  Ticker ? [ex: AAPL] : ").strip().upper()
    name   = getattr(args, "name", None)   or (ticker if not interactive else (input(f"  Nom complet ? [ex: Apple Inc.] : ").strip() or ticker))

    asset_class = getattr(args, "asset_class", None)
    if not asset_class:
        if not interactive:
            asset_class = "other"
        else:
            print("  Classe d'actif :")
            print("    1. equity   2. index   3. fx   4. crypto   5. indicator   6. other")
            cls_input = input("  Choix [1-6] : ").strip()
            classes = ["equity", "index", "fx", "crypto", "indicator", "other"]
            try:
                asset_class = classes[int(cls_input) - 1]
            except (ValueError, IndexError):
                asset_class = "other"

    currency = getattr(args, "currency", None) or (input("  Devise ? [ex: USD] : ").strip().upper() or "USD") if interactive else "USD"

    _csv_meta = {"provider": "tradingview", "currency": currency,
                 "asset_class": asset_class, "ticker": ticker}
    existing = normalizer.load_parquet(ticker, MARKET_DATA_DIR)
    if existing is not None:
        # Fusion : existant en premier, CSV nouveau en dernier → nouveau gagne sur chevauchement
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        print(f"  Fusion : {len(existing):,} existantes + {len(df):,} importées"
              f" = {len(combined):,} barres  ({combined.index.min().date()} -> {combined.index.max().date()})")
        normalizer.save_parquet(combined, ticker, asset_class, MARKET_DATA_DIR, source_meta=_csv_meta)
        catalog.register(ticker, name, asset_class, currency, "tradingview", combined)
        print(f"\n  OK '{ticker}' fusionné avec succès ({len(combined):,} barres).")
    else:
        normalizer.save_parquet(df, ticker, asset_class, MARKET_DATA_DIR, source_meta=_csv_meta)
        catalog.register(ticker, name, asset_class, currency, "tradingview", df)
        print(f"\n  OK '{ticker}' importé avec succès ({len(df):,} barres).")


def cmd_download(args) -> None:
    from databank.providers.yfinance_provider import YFinanceProvider
    from databank.normalizer import DataNormalizer
    from databank import catalog

    ticker     = args.ticker.upper()
    provider   = YFinanceProvider()
    normalizer = DataNormalizer()

    start = datetime.strptime(args.start, "%Y-%m-%d") if getattr(args, "start", None) else None
    end   = datetime.strptime(args.end,   "%Y-%m-%d") if getattr(args, "end",   None) else None

    df = provider.fetch(ticker, start=start, end=end)

    name     = getattr(args, "name", None)     or ticker
    cls_arg  = getattr(args, "asset_class", None)
    currency = getattr(args, "currency", None) or "USD"

    # Deviner la classe d'actif
    if cls_arg:
        asset_class = cls_arg
    elif ticker.startswith("^"):
        asset_class = "index"
    elif ticker.endswith("-USD") or ticker.endswith("USDT"):
        asset_class = "crypto"
    elif "=X" in ticker:
        asset_class = "fx"
    else:
        asset_class = "equity"

    # Mise à jour incrémentale si données existantes
    existing = normalizer.load_parquet(ticker, MARKET_DATA_DIR)
    _yf_meta = {"provider": "yfinance", "currency": currency,
                "asset_class": asset_class, "ticker": ticker}
    if existing is not None:
        path = normalizer.update_parquet(ticker, df, asset_class, MARKET_DATA_DIR)
        merged = normalizer.load_parquet(ticker, MARKET_DATA_DIR)
        # Re-écrire avec métadonnées après la fusion
        normalizer.save_parquet(merged, ticker, asset_class, MARKET_DATA_DIR, source_meta=_yf_meta)
        catalog.register(ticker, name, asset_class, currency, "yfinance", merged)
    else:
        path = normalizer.save_parquet(df, ticker, asset_class, MARKET_DATA_DIR, source_meta=_yf_meta)
        catalog.register(ticker, name, asset_class, currency, "yfinance", df)

    print(f"\n  OK '{ticker}' téléchargé et sauvegardé.")


def cmd_update(args) -> None:
    """Met à jour un ticker existant jusqu'à aujourd'hui."""
    from databank.normalizer import DataNormalizer

    ticker     = args.ticker.upper()
    normalizer = DataNormalizer()

    existing = normalizer.load_parquet(ticker, MARKET_DATA_DIR)
    if existing is None:
        print(f"  '{ticker}' introuvable dans la databank. Utilisez 'download' à la place.")
        sys.exit(1)

    last_date = existing.index.max().to_pydatetime()
    print(f"  Mise à jour de {ticker} depuis {last_date.date()}...")

    args.start = last_date.strftime("%Y-%m-%d")
    args.end   = None
    cmd_download(args)


def cmd_tv_import(args) -> None:
    """
    Importe tous les fichiers CSV d'un dossier TradingView en une seule commande.

    Règles de nommage TradingView : PREFIX_TICKER, 1D.csv
      CBOE_VIX, 1D.csv       -> VIX   (class: indicator)
      INDEX_NVLF, 1D.csv     -> NVLF  (class: indicator)
      USI_ADVDEC.NY, 1D.csv  -> ADVDEC.NY (class: indicator)
    """
    import re
    from databank.analyzer import CSVAnalyzer, ColumnMapping
    from databank.normalizer import DataNormalizer
    from databank import catalog

    folder     = Path(args.folder)
    analyzer   = CSVAnalyzer()
    normalizer = DataNormalizer()

    if not folder.exists():
        print(f"  Dossier introuvable : {folder}")
        return

    csv_files = sorted(folder.glob("*.csv"))
    if not csv_files:
        print(f"  Aucun fichier CSV trouvé dans {folder}")
        return

    print(f"\n  {len(csv_files)} fichier(s) trouvé(s) dans {folder}\n")

    ok, errors = 0, []

    for csv_path in csv_files:
        # Extraire le ticker depuis le nom de fichier : PREFIX_TICKER, 1D.csv
        stem   = csv_path.stem                    # ex: "CBOE_VIX, 1D" ou "USI_DVOL, 1D (1)"
        # Retire tout ce qui suit la première virgule (", 1D", ", 1D (1)", etc.)
        stem   = stem.split(",")[0].strip()       # ex: "CBOE_VIX" / "USI_DVOL"
        # Retire le préfixe jusqu'au dernier _ pour gérer NASDAQ_DLY_NDX -> NDX
        ticker = stem.rsplit("_", 1)[-1].strip() if "_" in stem else stem

        print(f"  [{csv_path.name}]  ->  ticker: {ticker}")

        try:
            mapping = analyzer.analyze(csv_path)

            # Profil TradingView : time,high,low,close (pas d'open, pas de volume)
            # Forcer le mapping si la détection auto n'est pas parfaite
            col_map = {}
            for col in mapping.column_map:
                col_lower = col.lower()
                if col_lower in ("time", "date", "timestamp"):
                    col_map[col] = "timestamp"
                elif col_lower == "open":
                    col_map[col] = "open"
                elif col_lower == "high":
                    col_map[col] = "high"
                elif col_lower == "low":
                    col_map[col] = "low"
                elif col_lower in ("close", "last"):
                    col_map[col] = "close"
                elif col_lower in ("volume", "vol"):
                    col_map[col] = "volume"
                else:
                    col_map[col] = None
            mapping.column_map = col_map

            asset_class = getattr(args, "asset_class", None) or "indicator"
            df = normalizer.normalize_from_csv(csv_path, mapping)
            _tv_meta = {"provider": "tradingview", "asset_class": asset_class, "ticker": ticker}
            existing = normalizer.load_parquet(ticker, MARKET_DATA_DIR)
            if existing is not None:
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
                normalizer.save_parquet(combined, ticker, asset_class, MARKET_DATA_DIR, source_meta=_tv_meta)
                catalog.register(ticker=ticker, name=ticker, asset_class=asset_class,
                                  currency="USD", provider="tradingview", df=combined)
                print(f"      FUSION  {len(existing):,} + {len(df):,} = {len(combined):,} barres"
                      f"  ({combined.index.min().date()} -> {combined.index.max().date()})")
            else:
                normalizer.save_parquet(df, ticker, asset_class, MARKET_DATA_DIR, source_meta=_tv_meta)
                catalog.register(ticker=ticker, name=ticker, asset_class=asset_class,
                                  currency="USD", provider="tradingview", df=df)
                print(f"      OK  {len(df):,} barres  ({df.index.min().date()} -> {df.index.max().date()})")
            ok += 1

        except Exception as e:
            print(f"      ERREUR : {e}")
            errors.append((csv_path.name, str(e)))

    print(f"\n  Résultat : {ok}/{len(csv_files)} fichiers importés.")
    if errors:
        print("  Echecs :")
        for name, err in errors:
            print(f"    - {name} : {err}")


def cmd_inspect(args) -> None:
    from databank.analyzer import CSVAnalyzer, display_mapping
    analyzer = CSVAnalyzer()
    mapping  = analyzer.analyze(Path(args.file))
    display_mapping(mapping)


def cmd_profiles(args) -> None:
    from databank.analyzer import list_profiles
    profiles = list_profiles()
    if not profiles:
        print("  Aucun profil sauvegardé.")
        return
    print(f"\n  Profils disponibles ({len(profiles)}) :")
    for p in profiles:
        print(f"    - {p}")
    print()


def cmd_derived(args) -> None:
    from databank.derived import DerivedSeriesManager
    manager = DerivedSeriesManager()
    sub = args.derived_cmd

    if sub == "add":
        manager.add(
            name=args.name,
            formula=args.formula,
            currency=getattr(args, "currency", "USD"),
            description=getattr(args, "description", ""),
        )
    elif sub == "remove":
        manager.remove(args.name)
    elif sub == "list":
        manager.print_list()
    elif sub == "compute":
        manager.compute(
            name=getattr(args, "name", None),
            start_date=getattr(args, "start", None),
            end_date=getattr(args, "end", None),
        )
    else:
        print(f"  Sous-commande inconnue : {sub}")


def cmd_reclassify(args) -> None:
    """Reclassifie un asset (met à jour le catalog et déplace le fichier Parquet)."""
    import shutil
    from databank import catalog as cat

    ticker    = args.ticker.upper()
    new_class = args.asset_class

    entry = cat.get(ticker)
    if not entry:
        print(f"  '{ticker}' introuvable dans le catalog.")
        return

    old_class = entry["class"]
    if old_class == new_class:
        print(f"  '{ticker}' est deja classe '{new_class}'.")
        return

    safe_ticker = ticker.replace("^", "_").replace("/", "_")
    old_path = MARKET_DATA_DIR / old_class / f"{safe_ticker}.parquet"
    new_dir  = MARKET_DATA_DIR / new_class
    new_path = new_dir / f"{safe_ticker}.parquet"

    if old_path.exists():
        new_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        print(f"  Fichier deplace : {old_class}/{safe_ticker}.parquet -> {new_class}/")
    else:
        print(f"  Fichier Parquet non trouve (catalog mis a jour quand meme).")

    cat.reclassify(ticker, new_class)
    print(f"  '{ticker}' reclassifie : {old_class} -> {new_class}")


def cmd_fred(args) -> None:
    """Importe une serie depuis FRED (derniere revision) ou ALFRED (premiere publication)."""
    from databank.providers.fred_provider import FREDProvider
    from databank.normalizer import DataNormalizer
    from databank.analyzer import detect_frequency
    from databank import catalog
    from databank.fred_config import get_api_key

    api_key = getattr(args, "api_key", None) or get_api_key()
    if not api_key:
        print("  Cle API FRED manquante.")
        print("  Configurez-la dans l'app ou via l'option --api-key.")
        sys.exit(1)

    series_id  = args.series_id.upper()
    mode       = getattr(args, "mode", "first")
    suffix     = "1ST" if mode == "first" else "REV"
    ticker     = getattr(args, "ticker", None) or f"{series_id}_{suffix}"
    asset_class = getattr(args, "asset_class", None) or "indicator"
    currency    = getattr(args, "currency", None) or "USD"

    provider   = FREDProvider()
    normalizer = DataNormalizer()

    # Infos serie
    print(f"\n  Serie : {series_id}  |  mode : {mode}")
    try:
        info = provider.get_series_info(series_id, api_key)
        series_name = info.get("title", ticker)
        print(f"  Titre     : {series_name}")
        print(f"  Frequence : {info.get('frequency_short', '?')}  |  "
              f"Unite : {info.get('units_short', '?')}")
    except Exception as e:
        print(f"  [!] Infos serie indisponibles : {e}")
        series_name = ticker

    name = getattr(args, "name", None) or series_name

    # Telechargement
    print(f"\n  Telechargement en cours...")
    df = provider.fetch(
        series_id=series_id,
        mode=mode,
        api_key=api_key,
        start_date=getattr(args, "start", None),
        end_date=getattr(args, "end", None),
    )

    # Resample si hebdo / mensuel
    freq = detect_frequency(df.index)
    if freq in ("weekly", "monthly"):
        print(f"  Frequence detectee : {freq} -> resampling daily (forward-fill).")
        df = df.resample("B").ffill().dropna(subset=["close"])

    _fred_provider = "alfred" if mode == "first" else "fred"
    normalizer.save_parquet(df, ticker, asset_class, MARKET_DATA_DIR,
                            source_meta={"provider": _fred_provider, "currency": currency,
                                         "asset_class": asset_class, "ticker": ticker,
                                         "series_id": series_id})
    catalog.register(ticker, name, asset_class, currency, "fred", df)
    print(f"\n  OK '{ticker}' importe ({len(df):,} barres, "
          f"{df.index.min().date()} -> {df.index.max().date()}).")


def cmd_breadth_init(args) -> None:
    """
    Initialise toutes les dérivées breadth standard en une seule commande.
    Télécharge aussi les VIX depuis Yahoo Finance si demandé.
    """
    from databank.derived import register_standard_derived

    print("\n  Enregistrement des dérivées breadth standard...")
    register_standard_derived()

    if getattr(args, "vix", False):
        print("\n  Téléchargement des indices VIX depuis Yahoo Finance...")
        for ticker in ["^VIX", "^VIX3M", "^VIX9D"]:
            print(f"\n  --- {ticker} ---")
            vix_args = argparse.Namespace(
                ticker=ticker,
                name={"^VIX": "CBOE VIX", "^VIX3M": "CBOE VIX 3-Month",
                      "^VIX9D": "CBOE VIX 9-Day"}[ticker],
                start=getattr(args, "from_date", "2010-01-01"),
                end=None,
                currency="USD",
                asset_class="indicator",
            )
            try:
                cmd_download(vix_args)
            except Exception as e:
                print(f"  Erreur pour {ticker}: {e}")

    print("\n  Prochaines étapes :")
    print("  1. Importer les CSVs breadth : python -m databank.updater import --file UVOL.csv")
    print("  2. Calculer les dérivées     : python -m databank.updater derived compute")
    print("  3. Vérifier                  : python -m databank.updater list --class indicator")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m databank.updater",
        description="Gestion de la databank de marché",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="Lister les assets disponibles")
    p_list.add_argument("--class", dest="asset_class", default=None)

    # import
    p_import = sub.add_parser("import", help="Importer un fichier CSV")
    p_import.add_argument("--file",            required=True)
    p_import.add_argument("--ticker",          default=None)
    p_import.add_argument("--name",            default=None)
    p_import.add_argument("--currency",        default=None)
    p_import.add_argument("--profile",         default=None, help="Nom d'un profil de mapping")
    p_import.add_argument("--non-interactive", dest="non_interactive", action="store_true",
                          help="Accepte automatiquement le mapping sans confirmation")
    p_import.add_argument("--class",           dest="asset_class", default=None,
                          choices=["equity", "index", "fx", "crypto", "indicator", "other"],
                          help="Classe d'actif (si absent, demande interactivement)")

    # download
    p_dl = sub.add_parser("download", help="Télécharger depuis Yahoo Finance")
    p_dl.add_argument("--ticker",   required=True)
    p_dl.add_argument("--name",     default=None)
    p_dl.add_argument("--from",     dest="start", default=None, metavar="YYYY-MM-DD")
    p_dl.add_argument("--to",       dest="end",   default=None, metavar="YYYY-MM-DD")
    p_dl.add_argument("--currency", default="USD")
    p_dl.add_argument("--class",    dest="asset_class", default=None)

    # update
    p_up = sub.add_parser("update", help="Mettre à jour un ticker existant")
    p_up.add_argument("--ticker", required=True)
    p_up.add_argument("--name",     default=None)
    p_up.add_argument("--currency", default="USD")
    p_up.add_argument("--class",    dest="asset_class", default=None)

    # inspect
    p_insp = sub.add_parser("inspect", help="Analyser un CSV sans l'importer")
    p_insp.add_argument("--file", required=True)

    # profiles
    sub.add_parser("profiles", help="Lister les profils de mapping")

    # derived
    p_der = sub.add_parser("derived", help="Gérer les séries dérivées")
    der_sub = p_der.add_subparsers(dest="derived_cmd", required=True)

    p_der_add = der_sub.add_parser("add", help="Déclarer une nouvelle dérivée")
    p_der_add.add_argument("--name",        required=True)
    p_der_add.add_argument("--formula",     required=True)
    p_der_add.add_argument("--currency",    default="USD")
    p_der_add.add_argument("--description", default="")

    p_der_rm = der_sub.add_parser("remove", help="Supprimer une dérivée")
    p_der_rm.add_argument("--name", required=True)

    der_sub.add_parser("list", help="Lister les dérivées définies")

    p_der_comp = der_sub.add_parser("compute", help="Calculer les dérivées")
    p_der_comp.add_argument("--name",  default=None, help="Si absent, calcule toutes les dérivées")
    p_der_comp.add_argument("--from",  dest="start", default=None, metavar="YYYY-MM-DD")
    p_der_comp.add_argument("--to",    dest="end",   default=None, metavar="YYYY-MM-DD")

    # tv-import
    p_tv = sub.add_parser("tv-import", help="Importer un dossier complet d'exports TradingView")
    p_tv.add_argument("--folder", required=True, help="Chemin vers le dossier contenant les CSV TradingView")
    p_tv.add_argument("--class", dest="asset_class", default="indicator",
                      help="Classe de tous les assets importés (indicator, index, equity, fx, crypto)")

    # reclassify
    p_rc = sub.add_parser("reclassify", help="Changer la classe d'un asset")
    p_rc.add_argument("--ticker",  required=True)
    p_rc.add_argument("--class",   dest="asset_class", required=True,
                      choices=["equity", "index", "fx", "crypto", "indicator", "other"])

    # breadth-init
    p_bi = sub.add_parser("breadth-init", help="Initialiser les dérivées breadth standard")
    p_bi.add_argument("--vix",  action="store_true", help="Télécharger aussi les VIX")
    p_bi.add_argument("--from", dest="from_date", default="2010-01-01", metavar="YYYY-MM-DD")

    # fred
    p_fred = sub.add_parser("fred", help="Importer une serie depuis FRED / ALFRED")
    p_fred.add_argument("--series",    dest="series_id", required=True,
                        help="Series ID FRED (ex: CPIAUCSL, UNRATE, GDP)")
    p_fred.add_argument("--mode",      default="first",
                        choices=["first", "latest"],
                        help="first=ALFRED premiere publication, latest=FRED derniere revision")
    p_fred.add_argument("--ticker",    default=None,
                        help="Nom du ticker dans la databank (defaut: SERIES_1ST ou SERIES_REV)")
    p_fred.add_argument("--name",      default=None,
                        help="Nom complet de la serie")
    p_fred.add_argument("--class",     dest="asset_class", default="indicator",
                        choices=["equity", "index", "fx", "crypto", "indicator", "other"])
    p_fred.add_argument("--currency",  default="USD")
    p_fred.add_argument("--from",      dest="start", default=None, metavar="YYYY-MM-DD")
    p_fred.add_argument("--to",        dest="end",   default=None, metavar="YYYY-MM-DD")
    p_fred.add_argument("--api-key",   dest="api_key", default=None,
                        help="Cle API FRED (optionnel si deja configuree)")

    args = parser.parse_args()

    dispatch = {
        "list":         cmd_list,
        "import":       cmd_import,
        "download":     cmd_download,
        "update":       cmd_update,
        "inspect":      cmd_inspect,
        "profiles":     cmd_profiles,
        "derived":      cmd_derived,
        "breadth-init": cmd_breadth_init,
        "tv-import":    cmd_tv_import,
        "reclassify":   cmd_reclassify,
        "fred":         cmd_fred,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
