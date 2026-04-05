"""
reporting/metrics.py — Calcul des métriques de performance.

Toutes les métriques sont calculées à partir de l'equity curve et des trades.
Aucune dépendance au moteur — peut être utilisé indépendamment.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

from backtest.portfolio.position import TradeRecord


def compute_metrics(
    equity_curve: pd.Series,
    trades: list[TradeRecord],
    initial_capital: float,
    risk_free_rate: float = 0.0,
) -> dict[str, float | int | str]:
    """
    Calcule toutes les métriques de performance.

    Args:
        equity_curve:    Série temporelle de l'équity (index=datetime, values=float).
        trades:          Liste des trades clôturés.
        initial_capital: Capital initial.
        risk_free_rate:  Taux sans risque annualisé (ex: 0.02 = 2%).

    Returns:
        Dict de métriques (valeurs float ou int, labels en snake_case).
    """
    if equity_curve.empty:
        return _empty_metrics()

    metrics: dict = {}

    # -----------------------------------------------------------------------
    # Rendement total et CAGR
    # -----------------------------------------------------------------------
    final_equity = float(equity_curve.iloc[-1])
    total_return = (final_equity - initial_capital) / initial_capital
    metrics["total_return_pct"]  = round(total_return * 100, 2)
    metrics["final_equity"]      = round(final_equity, 2)

    n_days = (equity_curve.index[-1] - equity_curve.index[0]).days
    n_years = n_days / 365.25 if n_days > 0 else 1.0
    if total_return > -1.0 and n_years > 0:
        cagr = (final_equity / initial_capital) ** (1.0 / n_years) - 1.0
    else:
        cagr = -1.0
    metrics["cagr_pct"] = round(cagr * 100, 2)

    # -----------------------------------------------------------------------
    # Drawdown
    # -----------------------------------------------------------------------
    rolling_max  = equity_curve.cummax()
    drawdown     = (equity_curve - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min())
    metrics["max_drawdown_pct"] = round(max_drawdown * 100, 2)

    # Durée du max drawdown
    dd_end    = drawdown.idxmin()
    dd_start  = equity_curve[:dd_end].idxmax()
    dd_days   = (dd_end - dd_start).days
    metrics["max_drawdown_duration_days"] = dd_days

    # -----------------------------------------------------------------------
    # Ratios de performance
    # -----------------------------------------------------------------------
    daily_returns = equity_curve.pct_change().dropna()

    if len(daily_returns) > 1 and daily_returns.std() > 0:
        # Nombre de périodes par an — estimation depuis la fréquence des données
        n_periods = _estimate_periods_per_year(equity_curve)
        excess_return = daily_returns.mean() - risk_free_rate / n_periods
        sharpe = excess_return / daily_returns.std() * math.sqrt(n_periods)
        metrics["sharpe_ratio"] = round(float(sharpe), 3)

        # Sortino — pénalise uniquement la volatilité négative
        neg_returns = daily_returns[daily_returns < 0]
        if len(neg_returns) > 0 and neg_returns.std() > 0:
            sortino = excess_return / neg_returns.std() * math.sqrt(n_periods)
            metrics["sortino_ratio"] = round(float(sortino), 3)
        else:
            metrics["sortino_ratio"] = float("inf")

        # Calmar = CAGR / max_drawdown
        if max_drawdown < 0:
            metrics["calmar_ratio"] = round(cagr / abs(max_drawdown), 3)
        else:
            metrics["calmar_ratio"] = float("inf")
    else:
        metrics["sharpe_ratio"]  = 0.0
        metrics["sortino_ratio"] = 0.0
        metrics["calmar_ratio"]  = 0.0

    # -----------------------------------------------------------------------
    # Statistiques sur les trades
    # -----------------------------------------------------------------------
    metrics["n_trades"] = len(trades)

    if not trades:
        metrics.update({
            "n_winners":         0,
            "n_losers":          0,
            "win_rate_pct":      0.0,
            "avg_win_pct":       0.0,
            "avg_loss_pct":      0.0,
            "profit_factor":     0.0,
            "avg_trade_pnl":     0.0,
            "total_commission":  0.0,
            "n_stop_loss":       0,
            "n_take_profit":     0,
            "n_signal_exit":     0,
        })
        return metrics

    pnls      = [t.pnl for t in trades]
    pnl_pcts  = [t.pnl_pct * 100 for t in trades]
    winners   = [t for t in trades if t.pnl > 0]
    losers    = [t for t in trades if t.pnl <= 0]

    metrics["n_winners"]    = len(winners)
    metrics["n_losers"]     = len(losers)
    metrics["win_rate_pct"] = round(len(winners) / len(trades) * 100, 1) if trades else 0.0

    metrics["avg_win_pct"]  = round(float(np.mean([t.pnl_pct * 100 for t in winners])), 2) if winners else 0.0
    metrics["avg_loss_pct"] = round(float(np.mean([t.pnl_pct * 100 for t in losers])), 2)  if losers  else 0.0

    gross_profit = sum(t.pnl for t in winners)
    gross_loss   = abs(sum(t.pnl for t in losers))
    metrics["profit_factor"]    = round(gross_profit / gross_loss, 3) if gross_loss > 0 else float("inf")
    metrics["avg_trade_pnl"]    = round(float(np.mean(pnls)), 2)
    metrics["total_commission"] = round(sum(t.total_commission for t in trades), 2)

    # Exit reason breakdown
    # "basket_stop_loss" / "basket_take_profit" are the basket-level variants
    # "signal_reverse" and "end_of_backtest" are folded into n_signal_exit so the
    # three counts always sum to n_trades.
    metrics["n_stop_loss"]   = sum(1 for t in trades if t.exit_reason in ("stop_loss",  "basket_stop_loss"))
    metrics["n_take_profit"] = sum(1 for t in trades if t.exit_reason in ("take_profit", "basket_take_profit"))
    metrics["n_signal_exit"] = sum(1 for t in trades if t.exit_reason not in (
        "stop_loss", "basket_stop_loss", "take_profit", "basket_take_profit"
    ))

    return metrics


def _estimate_periods_per_year(equity_curve: pd.Series) -> float:
    """Estime le nombre de périodes par an à partir de la fréquence des données."""
    if len(equity_curve) < 2:
        return 252.0
    avg_delta = (equity_curve.index[-1] - equity_curve.index[0]) / (len(equity_curve) - 1)
    days = avg_delta.days + avg_delta.seconds / 86400
    if days < 0.1:
        return 252.0 * 24  # données horaires
    elif days < 2:
        return 252.0       # données journalières
    elif days < 10:
        return 52.0        # données hebdomadaires
    else:
        return 12.0        # données mensuelles


def _empty_metrics() -> dict:
    return {
        "total_return_pct": 0.0, "final_equity": 0.0, "cagr_pct": 0.0,
        "max_drawdown_pct": 0.0, "max_drawdown_duration_days": 0,
        "sharpe_ratio": 0.0, "sortino_ratio": 0.0, "calmar_ratio": 0.0,
        "n_trades": 0, "n_winners": 0, "n_losers": 0, "win_rate_pct": 0.0,
        "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "profit_factor": 0.0,
        "avg_trade_pnl": 0.0, "total_commission": 0.0,
        "n_stop_loss": 0, "n_take_profit": 0, "n_signal_exit": 0,
    }


def print_metrics(metrics: dict, title: str = "Résultats du backtest") -> None:
    """Affiche les métriques dans la console de façon lisible."""
    sep = "-" * 50
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")
    print(f"  Capital final       : ${metrics.get('final_equity', 0):>12,.2f}")
    print(f"  Rendement total     : {metrics.get('total_return_pct', 0):>+10.2f}%")
    print(f"  CAGR                : {metrics.get('cagr_pct', 0):>+10.2f}%")
    print(sep)
    print(f"  Sharpe ratio        : {metrics.get('sharpe_ratio', 0):>12.3f}")
    print(f"  Sortino ratio       : {metrics.get('sortino_ratio', 0):>12.3f}")
    print(f"  Calmar ratio        : {metrics.get('calmar_ratio', 0):>12.3f}")
    print(sep)
    print(f"  Max drawdown        : {metrics.get('max_drawdown_pct', 0):>+10.2f}%")
    print(f"  Durée max drawdown  : {metrics.get('max_drawdown_duration_days', 0):>10} jours")
    print(sep)
    print(f"  Nombre de trades    : {metrics.get('n_trades', 0):>12}")
    print(f"  Taux de réussite    : {metrics.get('win_rate_pct', 0):>10.1f}%")
    print(f"  Profit factor       : {metrics.get('profit_factor', 0):>12.3f}")
    print(f"  Gain moyen          : {metrics.get('avg_win_pct', 0):>+10.2f}%")
    print(f"  Perte moyenne       : {metrics.get('avg_loss_pct', 0):>+10.2f}%")
    print(f"  Commissions totales : ${metrics.get('total_commission', 0):>11,.2f}")
    print(f"  Sorties stop loss   : {metrics.get('n_stop_loss', 0):>12}")
    print(f"  Sorties take profit : {metrics.get('n_take_profit', 0):>12}")
    print(f"  Sorties sur signal  : {metrics.get('n_signal_exit', 0):>12}")
    print(f"{'=' * 50}\n")
