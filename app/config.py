"""
config.py — Configuration du backtest.

Aucune valeur magique : tous les paramètres sont explicites ici.
Modifiez ce fichier pour changer le comportement sans toucher au code.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
MARKET_DATA_DIR = Path("DATASETS")
LOG_DIR         = Path("logs")

# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------
SYMBOLS    = ["AAPL"]          # Liste des tickers à backtester
START_DATE = "2018-01-01"      # Début de la période (inclusive)
END_DATE   = "2023-12-31"      # Fin de la période (inclusive)

# ---------------------------------------------------------------------------
# Capital
# ---------------------------------------------------------------------------
INITIAL_CAPITAL = 100_000.0    # En USD

# ---------------------------------------------------------------------------
# Commission
# ---------------------------------------------------------------------------
COMMISSION_RATE    = 0.001     # 0.1% de la valeur notionnelle par trade
COMMISSION_MINIMUM = 1.0       # Minimum 1 USD par trade

# ---------------------------------------------------------------------------
# Stratégie (SMACrossover)
# ---------------------------------------------------------------------------
SMA_FAST_PERIOD = 10
SMA_SLOW_PERIOD = 50

# ---------------------------------------------------------------------------
# Affichage / export
# ---------------------------------------------------------------------------
SHOW_CHART  = True             # Afficher la fenêtre matplotlib
SAVE_CHART  = True             # Sauvegarder le graphique en PNG
CHART_TITLE = f"SMA Crossover ({SMA_FAST_PERIOD}/{SMA_SLOW_PERIOD}) — {SYMBOLS}"
