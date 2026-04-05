"""
main.py — Lance un backtest end-to-end.

Étapes :
  1. Si les données ne sont pas dans la databank, génère des données synthétiques
     pour la démonstration (ou utilise la databank si disponible).
  2. Construit tous les composants du moteur.
  3. Lance le backtest.
  4. Affiche les métriques et les graphiques.

Pour utiliser vos propres données :
  python -m databank.updater download --ticker AAPL --from 2018-01-01
  → puis relancer main.py
"""

from __future__ import annotations

import io
import logging
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 sur les terminaux Windows (cp1252 par défaut)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

import config
from backtest.core.queue import EventQueue
from backtest.data.handler import DataBankHandler, RawCSVHandler
from backtest.engine import BacktestEngine
from backtest.execution.simulated import CommissionConfig, SimulatedExecutionHandler
from backtest.portfolio.base import SimplePortfolio
from backtest.reporting.charts import plot_results
from backtest.reporting.metrics import print_metrics
from backtest.risk.rules import StandardRiskManager
from strategies.sma_crossover import SMACrossover


# ---------------------------------------------------------------------------
# Génération de données synthétiques (demo)
# ---------------------------------------------------------------------------

def generate_synthetic_csv(
    ticker: str,
    start: str,
    end: str,
    seed: int = 42,
) -> Path:
    """
    Génère un CSV OHLCV synthétique par marche aléatoire.
    Utilisé uniquement si les données réelles ne sont pas disponibles.
    """
    path = Path(f"DATASETS/_demo/{ticker}_synthetic.csv")
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        return path

    rng   = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start, end=end)
    n     = len(dates)

    # Marche aléatoire avec drift positif
    log_returns = rng.normal(0.0003, 0.015, n)
    prices      = 150.0 * np.exp(np.cumsum(log_returns))

    intraday_noise = rng.uniform(0.005, 0.02, n)
    highs  = prices * (1 + intraday_noise)
    lows   = prices * (1 - intraday_noise)
    opens  = lows + rng.uniform(0, 1, n) * (highs - lows)
    volume = rng.integers(500_000, 5_000_000, n)

    df = pd.DataFrame({
        "Date":   dates,
        "Open":   opens.round(2),
        "High":   highs.round(2),
        "Low":    lows.round(2),
        "Close":  prices.round(2),
        "Volume": volume,
    })
    df.to_csv(path, index=False)
    print(f"  Données synthétiques générées : {path} ({n} barres)")
    return path


# ---------------------------------------------------------------------------
# Construction du moteur
# ---------------------------------------------------------------------------

def build_engine(symbol: str) -> BacktestEngine:
    queue = EventQueue()
    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # Data handler — essaie la databank, sinon génère des données synthétiques
    try:
        data = DataBankHandler(
            symbols=[symbol],
            queue=queue,
            market_data_dir=config.MARKET_DATA_DIR,
            start_date=datetime.strptime(config.START_DATE, "%Y-%m-%d"),
            end_date=datetime.strptime(config.END_DATE, "%Y-%m-%d"),
        )
        print(f"  Données chargées depuis la databank : {symbol}")
    except FileNotFoundError:
        print(f"  '{symbol}' absent de la databank — utilisation de données synthétiques.")
        print(f"  Pour des données réelles : python -m databank.updater download --ticker {symbol} --from {config.START_DATE}")
        csv_path = generate_synthetic_csv(symbol, config.START_DATE, config.END_DATE)
        data = RawCSVHandler(
            symbol=symbol,
            csv_path=csv_path,
            queue=queue,
            start_date=datetime.strptime(config.START_DATE, "%Y-%m-%d"),
            end_date=datetime.strptime(config.END_DATE, "%Y-%m-%d"),
        )

    # Composants
    commission = CommissionConfig(
        rate=config.COMMISSION_RATE,
        minimum=config.COMMISSION_MINIMUM,
    )
    portfolio  = SimplePortfolio(initial_capital=config.INITIAL_CAPITAL, data=data)
    risk       = StandardRiskManager()
    execution  = SimulatedExecutionHandler(data=data, queue=queue, commission=commission)

    # Stratégie
    strategy             = SMACrossover(data=data, queue=queue)
    strategy.fast_period = config.SMA_FAST_PERIOD
    strategy.slow_period = config.SMA_SLOW_PERIOD

    return BacktestEngine(
        data=data,
        strategies=[strategy],
        portfolio=portfolio,
        risk=risk,
        execution=execution,
        queue=queue,
        initial_capital=config.INITIAL_CAPITAL,
        log_dir=config.LOG_DIR,
        run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    symbol = config.SYMBOLS[0]

    print(f"\n{'=' * 55}")
    print(f"  BACKTEST — {symbol}")
    print(f"  Période : {config.START_DATE} → {config.END_DATE}")
    print(f"  Capital : ${config.INITIAL_CAPITAL:,.0f}")
    print(f"  Stratégie : SMACrossover({config.SMA_FAST_PERIOD}, {config.SMA_SLOW_PERIOD})")
    print(f"{'=' * 55}\n")

    engine = build_engine(symbol)
    result = engine.run()

    # Affichage des métriques
    print_metrics(result.metrics, title=f"SMACrossover — {symbol}")

    # Affichage des trades (10 derniers)
    if result.trades:
        print(f"  Derniers trades ({min(10, len(result.trades))} / {len(result.trades)}) :")
        print(f"  {'Date entrée':<12} {'Date sortie':<12} {'Sens':<6} {'Entrée':>8} {'Sortie':>8} {'PnL':>10} {'Raison'}")
        print(f"  {'-'*12} {'-'*12} {'-'*6} {'-'*8} {'-'*8} {'-'*10} {'-'*12}")
        for t in result.trades[-10:]:
            print(
                f"  {str(t.entry_time.date()):<12} "
                f"{str(t.exit_time.date()):<12} "
                f"{t.direction.value:<6} "
                f"{t.entry_price:>8.2f} "
                f"{t.exit_price:>8.2f} "
                f"{t.pnl:>+10.2f} "
                f"{t.exit_reason}"
            )
        print()

    # Graphiques
    save_path = config.LOG_DIR / f"{result.run_id}_{symbol}.png" if config.SAVE_CHART else None
    plot_results(
        equity_curve=result.equity_curve,
        trades=result.trades,
        metrics=result.metrics,
        title=config.CHART_TITLE,
        save_path=save_path,
        show=config.SHOW_CHART,
    )


if __name__ == "__main__":
    main()
