"""
menu.py — Interface interactive du moteur de backtest.

Lance avec : python menu.py
Navigue avec les chiffres, Entrée pour valider.
"""

from __future__ import annotations

import io
import os
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 sur les terminaux Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Se placer dans le dossier du projet, quel que soit l'endroit d'où on lance
os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Helpers UI
# ---------------------------------------------------------------------------

W = 56   # largeur de la boîte

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def header(title: str = "BACKTEST ENGINE"):
    print("=" * W)
    print(f"  {title}")
    print("=" * W)

def section(title: str):
    print(f"\n  -- {title} --")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix} : ").strip()
    return val if val else default

def ask_int(prompt: str, default: int) -> int:
    val = ask(prompt, str(default))
    try:
        return int(val)
    except ValueError:
        return default

def ask_float(prompt: str, default: float) -> float:
    val = ask(prompt, str(default))
    try:
        return float(val)
    except ValueError:
        return default

def ask_choice(options: list[str], back: bool = True) -> int:
    """Affiche une liste numérotée, retourne l'index (0-based) ou -1 pour Retour."""
    for i, opt in enumerate(options, 1):
        print(f"    {i}. {opt}")
    if back:
        print(f"    0. Retour")
    while True:
        raw = input("  > ").strip()
        if raw == "0" and back:
            return -1
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print("  Choix invalide.")

def pause(msg: str = "Appuyez sur Entrée pour continuer..."):
    input(f"\n  {msg}")


# ---------------------------------------------------------------------------
# Menu principal
# ---------------------------------------------------------------------------

def main_menu():
    while True:
        clear()
        header()
        print()
        print("    1.  Lancer un backtest")
        print("    2.  Creer une nouvelle strategie")
        print("    3.  Databank")
        print("    4.  Voir les resultats")
        print()
        print("    0.  Quitter")
        print()
        choice = ask("Votre choix")

        if choice == "1":
            menu_backtest()
        elif choice == "2":
            menu_strategy_builder()
        elif choice == "3":
            menu_databank()
        elif choice == "4":
            menu_results()
        elif choice == "0":
            print("\n  Au revoir.\n")
            break
        else:
            pass  # boucle


# ---------------------------------------------------------------------------
# Menu Backtest
# ---------------------------------------------------------------------------

def menu_backtest():
    clear()
    header("BACKTEST")
    print()

    # 1. Choisir la stratégie
    strategies = _list_strategies()
    if not strategies:
        print("  Aucune stratégie disponible dans strategies/")
        pause()
        return

    section("Stratégie")
    idx = ask_choice(strategies)
    if idx == -1:
        return
    strategy_name = strategies[idx]

    # Charger les valeurs par défaut de la stratégie
    strat_defaults = _load_strategy_defaults(strategy_name)

    # 2. Choisir les symboles disponibles (assets tradeable uniquement)
    section("Symbole(s) a backtester")
    available = _list_tickers(tradeable_only=True)
    if not available:
        available = _list_tickers()
    if not available:
        print("  Databank vide. Importez des données d'abord (menu Databank).")
        pause()
        return

    # Pré-sélectionner le symbole intégré dans la stratégie si disponible
    default_symbol = strat_defaults.get("symbol", "")
    if default_symbol and default_symbol in available:
        print(f"  Symbole de la strategie : {default_symbol}")
        override = ask("Utiliser un autre symbole ? (o/N)", "N").lower()
        if override in ("o", "oui", "y", "yes"):
            idx2 = ask_choice(available)
            if idx2 == -1:
                return
            symbol = available[idx2]
        else:
            symbol = default_symbol
    else:
        idx2 = ask_choice(available)
        if idx2 == -1:
            return
        symbol = available[idx2]

    # 3. Période et capital
    section("Période et capital")
    start = ask("Date de début  (YYYY-MM-DD)", "2018-01-01")
    end   = ask("Date de fin    (YYYY-MM-DD)", "2023-12-31")
    cap   = ask_float("Capital initial ($)", 100_000.0)
    comm  = ask_float("Commission     (ex: 0.001 = 0.1%)", 0.001)

    # 4. Paramètres de risque — pré-remplis depuis la stratégie
    section("Parametres de risque  (Entree = valeur de la strategie)")

    d_psize = strat_defaults.get("position_size", 0.10)
    d_sl    = strat_defaults.get("stop_loss")
    d_tp    = strat_defaults.get("take_profit")

    def _fmt_pct(v):
        return f"{v*100:.1f}%" if v is not None else "aucun"

    print(f"  Valeurs definies dans la strategie :")
    print(f"    Position size : {_fmt_pct(d_psize)}")
    print(f"    Stop loss     : {_fmt_pct(d_sl)}")
    print(f"    Take profit   : {_fmt_pct(d_tp)}")
    print(f"  Entree = conserver la valeur de la strategie | tapez une valeur pour remplacer | 'aucun' pour desactiver")
    print()

    psize_str = ask(f"Position size", str(d_psize))
    psize = float(psize_str) if psize_str else d_psize

    sl_default = str(d_sl) if d_sl is not None else "aucun"
    sl = ask(f"Stop loss     ", sl_default)

    tp_default = str(d_tp) if d_tp is not None else "aucun"
    tp = ask(f"Take profit   ", tp_default)

    stop_loss   = _parse_pct(sl)
    take_profit = _parse_pct(tp)

    # 5. Confirmation
    clear()
    header("CONFIRMATION")
    print(f"\n  Strategie    : {strategy_name}")
    print(f"  Symbole      : {symbol}")
    print(f"  Periode      : {start}  ->  {end}")
    print(f"  Capital      : ${cap:,.0f}")
    print(f"  Position     : {psize*100:.0f}% du capital")
    print(f"  Stop loss    : {stop_loss*100:.1f}%" if stop_loss else "  Stop loss    : aucun")
    print(f"  Take profit  : {take_profit*100:.1f}%" if take_profit else "  Take profit  : aucun")
    print(f"  Commission   : {comm*100:.2f}%")
    print()
    go = ask("Lancer le backtest ? (O/n)", "O").lower()
    if go in ("n", "non", "no"):
        return

    # 6. Lancement
    _run_backtest(
        strategy_name=strategy_name,
        symbol=symbol,
        start=start,
        end=end,
        capital=cap,
        position_size=psize,
        stop_loss=stop_loss,
        take_profit=take_profit,
        commission_rate=comm,
    )


def _run_backtest(
    strategy_name: str,
    symbol: str,
    start: str,
    end: str,
    capital: float,
    position_size: float,
    stop_loss,
    take_profit,
    commission_rate: float,
):
    clear()
    header("BACKTEST EN COURS")
    print(f"\n  {strategy_name} — {symbol}  ({start} -> {end})\n")

    try:
        import importlib
        import logging
        logging.disable(logging.WARNING)   # silencer les logs pendant l'UI

        from backtest.core.queue import EventQueue
        from backtest.data.handler import DataBankHandler
        from backtest.engine import BacktestEngine
        from backtest.execution.simulated import CommissionConfig, SimulatedExecutionHandler
        from backtest.portfolio.base import SimplePortfolio
        from backtest.reporting.charts import plot_results
        from backtest.reporting.metrics import print_metrics
        from backtest.risk.rules import StandardRiskManager

        # Charger la stratégie dynamiquement
        mod = importlib.import_module(f"strategies.{strategy_name}")
        klass = _find_strategy_class(mod)
        if klass is None:
            print(f"  Impossible de trouver une classe BaseStrategy dans strategies/{strategy_name}.py")
            pause()
            return

        queue = EventQueue()
        run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        data = DataBankHandler(
            symbols=[symbol],
            queue=queue,
            market_data_dir=Path("DATASETS"),
            start_date=datetime.strptime(start, "%Y-%m-%d"),
            end_date=datetime.strptime(end, "%Y-%m-%d"),
        )

        strategy = klass(data=data, queue=queue)
        strategy.position_size = position_size
        strategy.stop_loss     = stop_loss
        strategy.take_profit   = take_profit

        portfolio = SimplePortfolio(initial_capital=capital, data=data)
        risk      = StandardRiskManager()
        execution = SimulatedExecutionHandler(
            data=data, queue=queue,
            commission=CommissionConfig(rate=commission_rate),
        )

        engine = BacktestEngine(
            data=data, strategies=[strategy], portfolio=portfolio,
            risk=risk, execution=execution, queue=queue,
            initial_capital=capital, log_dir=Path("logs"), run_id=run_id,
        )

        print("  Calcul en cours...\n")
        result = engine.run()

        logging.disable(logging.NOTSET)
        clear()
        header(f"RESULTATS — {strategy_name} / {symbol}")
        print_metrics(result.metrics, title=f"{strategy_name} — {symbol}")

        # Derniers trades
        if result.trades:
            n = min(10, len(result.trades))
            print(f"  Derniers trades ({n} / {len(result.trades)}) :")
            print(f"  {'Entree':<12} {'Sortie':<12} {'Sens':<6} {'Prix E':>8} {'Prix S':>8} {'PnL':>10}  Raison")
            print(f"  {'-'*12} {'-'*12} {'-'*6} {'-'*8} {'-'*8} {'-'*10}  {'-'*12}")
            for t in result.trades[-n:]:
                print(
                    f"  {str(t.entry_time.date()):<12} "
                    f"{str(t.exit_time.date()):<12} "
                    f"{t.direction.value:<6} "
                    f"{t.entry_price:>8.2f} "
                    f"{t.exit_price:>8.2f} "
                    f"{t.pnl:>+10.2f}  "
                    f"{t.exit_reason}"
                )

        print()
        show_chart = ask("Afficher le graphique ? (O/n)", "O").lower()
        if show_chart not in ("n", "non", "no"):
            save_path = Path("logs") / f"{run_id}_{symbol}.png"
            plot_results(
                equity_curve=result.equity_curve,
                trades=result.trades,
                metrics=result.metrics,
                title=f"{strategy_name} — {symbol}  ({start} -> {end})",
                save_path=save_path,
                show=True,
            )

    except FileNotFoundError as e:
        print(f"\n  ERREUR : {e}")
    except Exception as e:
        import traceback
        print(f"\n  ERREUR inattendue : {e}")
        traceback.print_exc()

    pause()


# ---------------------------------------------------------------------------
# Menu Strategy Builder
# ---------------------------------------------------------------------------

def menu_strategy_builder():
    try:
        from strategy_builder import StrategyWizard
        StrategyWizard().run()
    except Exception as e:
        import traceback
        print(f"\n  ERREUR : {e}")
        traceback.print_exc()
        pause()


# ---------------------------------------------------------------------------
# Menu Databank
# ---------------------------------------------------------------------------

def menu_databank():
    while True:
        clear()
        header("DATABANK")
        print()
        print("    1.  Importer un dossier TradingView")
        print("    2.  Importer un fichier CSV")
        print("    3.  Voir les donnees disponibles")
        print("    4.  Series derivees")
        print("    5.  Reclasser un asset  (ex: indicateur -> index)")
        print()
        print("    0.  Retour")
        print()
        choice = ask("Votre choix")

        if choice == "1":
            _databank_tv_import()
        elif choice == "2":
            _databank_csv_import()
        elif choice == "3":
            _databank_list()
        elif choice == "4":
            menu_derived()
        elif choice == "5":
            _databank_reclassify()
        elif choice == "0":
            break


def _databank_tv_import():
    clear()
    header("IMPORT TRADINGVIEW")
    print()
    folder = ask("Chemin du dossier TradingView", "TradingView 02")
    if not Path(folder).exists():
        print(f"\n  Dossier introuvable : {folder}")
        pause()
        return
    print()
    import subprocess
    subprocess.run([sys.executable, "-m", "databank.updater", "tv-import", "--folder", folder])
    pause()


def _databank_csv_import():
    clear()
    header("IMPORT CSV")
    print()
    file_path = ask("Chemin du fichier CSV")
    if not file_path or not Path(file_path).exists():
        print(f"\n  Fichier introuvable : {file_path}")
        pause()
        return
    print()
    import subprocess
    subprocess.run([sys.executable, "-m", "databank.updater", "import", "--file", file_path])
    pause()


def _databank_list():
    clear()
    header("DONNÉES DISPONIBLES")
    print()
    import subprocess
    subprocess.run([sys.executable, "-m", "databank.updater", "list"])
    pause()


def _databank_reclassify():
    clear()
    header("RECLASSER UN ASSET")
    print()
    import subprocess
    subprocess.run([sys.executable, "-m", "databank.updater", "list"])
    print()
    ticker = ask("Ticker a reclasser").upper()
    if not ticker:
        pause()
        return
    print("  Nouvelle classe :")
    classes = ["index", "equity", "fx", "crypto", "indicator", "other"]
    idx = ask_choice(classes)
    if idx == -1:
        return
    new_class = classes[idx]
    subprocess.run([
        sys.executable, "-m", "databank.updater", "reclassify",
        "--ticker", ticker, "--class", new_class,
    ])
    pause()


def menu_derived():
    while True:
        clear()
        header("SERIES DERIVEES")
        print()
        print("    1.  Voir les derivees definies")
        print("    2.  Calculer / recalculer les derivees")
        print("    3.  Ajouter une derivee")
        print("    4.  Supprimer une derivee")
        print()
        print("    0.  Retour")
        print()
        choice = ask("Votre choix")

        if choice == "1":
            clear()
            import subprocess
            subprocess.run([sys.executable, "-m", "databank.updater", "derived", "list"])
            pause()
        elif choice == "2":
            clear()
            print("  Calcul en cours...\n")
            import subprocess
            subprocess.run([sys.executable, "-m", "databank.updater", "derived", "compute"])
            pause()
        elif choice == "3":
            clear()
            header("AJOUTER UNE DERIVEE")
            print()
            name    = ask("Nom de la serie (ex: MON_RATIO)").upper()
            formula = ask("Formule        (ex: UVOL / (UVOL + DVOL))")
            desc    = ask("Description    (optionnel)")
            if name and formula:
                import subprocess
                cmd = [sys.executable, "-m", "databank.updater", "derived", "add",
                       "--name", name, "--formula", formula]
                if desc:
                    cmd += ["--description", desc]
                subprocess.run(cmd)
            pause()
        elif choice == "4":
            clear()
            header("SUPPRIMER UNE DERIVEE")
            print()
            import subprocess
            subprocess.run([sys.executable, "-m", "databank.updater", "derived", "list"])
            name = ask("\n  Nom a supprimer").upper()
            if name:
                subprocess.run([sys.executable, "-m", "databank.updater", "derived", "remove", "--name", name])
            pause()
        elif choice == "0":
            break


# ---------------------------------------------------------------------------
# Menu Résultats
# ---------------------------------------------------------------------------

def menu_results():
    clear()
    header("DERNIERS RESULTATS")
    print()

    logs = sorted(Path("logs").glob("*_audit.json"), reverse=True)
    pngs = sorted(Path("logs").glob("*.png"), reverse=True)

    if not logs and not pngs:
        print("  Aucun résultat disponible. Lancez d'abord un backtest.")
        pause()
        return

    if pngs:
        section("Graphiques disponibles")
        options = [p.name for p in pngs[:10]]
        idx = ask_choice(options)
        if idx == -1:
            return
        path = pngs[idx]
        print(f"\n  Ouverture de {path.name}...")
        if os.name == "nt":
            os.startfile(str(path))
        else:
            import subprocess
            subprocess.run(["xdg-open", str(path)])
    pause()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_strategies() -> list[str]:
    strats = []
    for p in sorted(Path("strategies").glob("*.py")):
        if p.name.startswith("_"):
            continue
        strats.append(p.stem)
    return strats


def _list_tickers(tradeable_only: bool = False) -> list[str]:
    from databank.catalog import list_assets
    assets = list_assets()
    if tradeable_only:
        tradeable = {"index", "equity", "fx", "crypto"}
        assets = [e for e in assets if e.get("class") in tradeable]
    return sorted(e["ticker"] for e in assets)


def _parse_pct(val: str):
    """Convertit une saisie en float ou None. Accepte '', 'vide', 'aucun', 'none', 'no'."""
    if not val or val.strip().lower() in ("vide", "aucun", "none", "no", "n", "-", "0"):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _load_strategy_defaults(strategy_name: str) -> dict:
    """Charge les attributs de classe d'une stratégie (position_size, stop_loss, etc.)."""
    try:
        import importlib
        mod = importlib.import_module(f"strategies.{strategy_name}")
        klass = _find_strategy_class(mod)
        if klass is None:
            return {}
        # Lire le symbole depuis le fichier source (ligne "Asset : NDX")
        symbol = ""
        try:
            import re
            src = Path("strategies") / f"{strategy_name}.py"
            txt = src.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"Asset\s*:\s*(\S+)", txt)
            if m:
                symbol = m.group(1)
        except Exception:
            pass
        return {
            "position_size": getattr(klass, "position_size", 0.10),
            "stop_loss":     getattr(klass, "stop_loss",     None),
            "take_profit":   getattr(klass, "take_profit",   None),
            "symbol":        symbol,
        }
    except Exception:
        return {}


def _find_strategy_class(mod):
    import inspect
    from backtest.strategy.base import BaseStrategy
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
            return obj
    return None


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main_menu()
