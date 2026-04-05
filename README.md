README.md
Post Reddit
Show HN
Topics GitHub
À coller directement dans README.md à la racine du repo. Remplace les screenshots par tes propres captures. Les badges sont optionnels.

Copier
# Sextant — Event-Driven Backtesting Engine

> A local, Python-based backtesting application with a Streamlit interface. Test trading strategies on historical data without depending on third-party platforms.

![Sextant interface screenshot](main/sextant.png)

## Features

**Strict bar-by-bar event loop** — `MarketEvent → SignalEvent → OrderEvent → FillEvent`. Deterministic: identical dataset + config always produces identical results. Full JSON audit log of every event.

**Risk management**
- 3 execution modes: Netting, Netting Delay, Hedge (long/short coexist)
- Stop loss, take profit, basket SL/TP (group positions under a shared stop)
- Position sizing as % of current capital

**Performance metrics** — Total return, CAGR, Sharpe, Sortino, Calmar, max drawdown (amount + duration), win rate, profit factor, avg win/loss, exit reason breakdown (stop / TP / signal), total commissions.

**14 built-in indicators** — SMA, EMA, RSI, ATR, Bollinger Bands, Stoch%K, Momentum, ROC, Highest High, Lowest Low, VWAP, RAW. Extensible via `register_indicator()`.

**No-code strategy builder** — Visual IF/THEN condition builder with AND logic, `crosses_above`/`crosses_below` operators, and real-time preview of the latest value for any selected series.

**Multi-source databank**
- CSV import (TradingView export format)
- Yahoo Finance — indices, equities, FX, crypto, VIX, full history from 1990
- FRED / ALFRED — economic time series with vintage support and client-side transforms (YoY%, MoM%, absolute changes)
- Derived series (ratios, custom %)

## Quick Start

```bash
# 1. Clone
git clone https://github.com/raphaub-hub/sextant.git
cd sextant

# 2. Install (Windows)
install.bat

# 3. Run
streamlit run app.py
```

## What this is NOT

- No live trading / broker connection
- No parameter optimization (grid search, walk-forward) — yet
- No multi-timeframe (daily only for now)
- No options / derivatives
- Simplified slippage: execution at bar close
- No cloud, no SaaS, no REST API — this is a local desktop tool
- No portfolio optimization (Markowitz etc.)
- No tick / intraday data

## Stack

Python 3.10+, Streamlit, Pandas, NumPy, Plotly, yfinance, PyArrow (Parquet), openpyxl.

Abstract interfaces: `AbstractDataHandler`, `AbstractPortfolio`, `AbstractRiskManager`, `AbstractExecutionHandler`, `AbstractProvider`.

## Use case

Personal use / research. For anyone who wants to test strategy ideas on historical data without depending on a third-party tool.

---

*Built with [Claude Code](https://claude.ai/code)*
