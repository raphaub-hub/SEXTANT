"""Script de backtest demo_all_features."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from datetime import datetime
from pathlib import Path

from backtest.core.queue import EventQueue
from backtest.data.handler import DataBankHandler
from backtest.engine import BacktestEngine
from backtest.execution.simulated import CommissionConfig, SimulatedExecutionHandler
from backtest.portfolio.base import SimplePortfolio
from backtest.risk.rules import ExecutionMode, StandardRiskManager
from backtest.strategy.base import BaseStrategy
import importlib, inspect

# Recalcul des dérivées nécessaires
from databank.derived import DerivedSeriesManager
dm   = DerivedSeriesManager()
defs = dm._load_defs()
for s in ["UVOL_PCT"]:
    if s in defs:
        dm.compute(name=s)

# Chargement de la stratégie
mod   = importlib.import_module("strategies.demo_all_features")
klass = next(
    obj for _, obj in inspect.getmembers(mod, inspect.isclass)
    if issubclass(obj, BaseStrategy) and obj is not BaseStrategy
)

symbols = ["NDX", "SPX", "NVLF", "UVOL_PCT"]
queue   = EventQueue()
data    = DataBankHandler(
    symbols=symbols, queue=queue,
    market_data_dir=Path("DATASETS"),
    start_date=datetime(2012, 1, 1),
    end_date=datetime(2025, 12, 31),
)
strategy  = klass(data=data, queue=queue)
portfolio = SimplePortfolio(initial_capital=100_000.0, data=data)
risk      = StandardRiskManager(execution_mode=ExecutionMode.NETTING)
execution = SimulatedExecutionHandler(
    data=data, queue=queue,
    commission=CommissionConfig(rate=0.001),
)
engine = BacktestEngine(
    data=data, strategies=[strategy], portfolio=portfolio,
    risk=risk, execution=execution, queue=queue,
    initial_capital=100_000.0,
    log_dir=Path("logs"), run_id="demo_all_features",
)

print("Running backtest 2012-2025...")
result = engine.run()

# Métriques
print("\n" + "="*52)
print("  RESULTS — demo_all_features  (2012 → 2025)")
print("="*52)
for k, v in result.metrics.items():
    if isinstance(v, float):
        print(f"  {k:<32} {v:>10.4f}")
    else:
        print(f"  {k:<32} {str(v):>10}")

print(f"\n  Trades total    : {len(result.trades)}")
print(f"  Capital initial : {result.equity_curve.iloc[0]:>10.0f} $")
print(f"  Capital final   : {result.equity_curve.iloc[-1]:>10.0f} $")
