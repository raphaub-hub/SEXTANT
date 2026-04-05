"""
reporting/charts.py — Static charts via matplotlib.

Panels (dynamic based on options):
  1. Equity curve (always)
  2. Outperformance % vs benchmark (optional, requires benchmark)
  3. Drawdown % (optional)
  4. Compact metrics bar (optional)

Usage:
    fig = plot_results(equity_curve, trades, metrics, show=False)  # returns figure
    plot_results(equity_curve, trades, metrics)                     # shows interactively
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def plot_results(
    equity_curve: pd.Series,
    trades,
    metrics: dict,
    title: str = "Backtest Results",
    benchmark: Optional[pd.Series] = None,       # normalized Series, same index range
    benchmark_label: str = "Benchmark",
    show_trades: bool = True,                     # show entry/exit markers on equity
    show_drawdown: bool = True,                   # show drawdown panel
    show_outperformance: bool = True,             # show outperformance panel (only if benchmark given)
    show_equity_ma: int = 0,                      # if > 0, overlay a rolling MA of this period on equity
    log_scale: bool = False,                      # log scale on equity y-axis
    save_path=None,
    show: bool = True,
    show_metrics_bar: bool = True,
) -> Optional["Figure"]:
    """
    Generate equity curve chart with optional benchmark, outperformance,
    drawdown and metrics panels.

    Returns the matplotlib Figure when show=False so callers can embed it
    (e.g. st.pyplot(fig) in Streamlit).  Returns None when show=True.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import matplotlib.dates as mdates
        import matplotlib.ticker as mticker
    except ImportError:
        raise ImportError("matplotlib is required: pip install matplotlib")

    if equity_curve.empty:
        print("Empty equity curve — no chart generated.")
        return None

    # -----------------------------------------------------------------------
    # Pre-computations
    # -----------------------------------------------------------------------
    rolling_max = equity_curve.cummax()
    drawdown    = (equity_curve - rolling_max) / rolling_max * 100

    # Outperformance series (only when benchmark provided and requested)
    outperf_series: Optional[pd.Series] = None
    bench_norm: Optional[pd.Series] = None
    if benchmark is not None and show_outperformance:
        bench_aligned = benchmark.reindex(equity_curve.index, method="ffill")
        # Drop leading NaNs
        bench_aligned = bench_aligned.dropna()
        if not bench_aligned.empty:
            common_start = max(equity_curve.index[0], bench_aligned.index[0])
            eq_trimmed    = equity_curve.loc[common_start:]
            bm_trimmed    = bench_aligned.loc[common_start:]
            eq_norm       = eq_trimmed / eq_trimmed.iloc[0]
            bench_norm    = bm_trimmed / bm_trimmed.iloc[0]
            # Reindex bench_norm to full equity index for the outperf panel
            bench_norm_full = bench_norm.reindex(equity_curve.index, method="ffill")
            eq_norm_full    = equity_curve / equity_curve.iloc[0]
            outperf_series  = (eq_norm_full / bench_norm_full - 1) * 100

    # -----------------------------------------------------------------------
    # Build dynamic panel list
    # -----------------------------------------------------------------------
    panels: list[tuple[str, float]] = []
    panels.append(("equity", 3.0))
    if outperf_series is not None:
        panels.append(("outperf", 1.2))
    if show_drawdown:
        panels.append(("drawdown", 1.5))
    if show_metrics_bar:
        panels.append(("metrics", 0.45))

    n_panels      = len(panels)
    height_ratios = [p[1] for p in panels]
    total_h       = sum(height_ratios)
    fig_height    = max(4, total_h * 1.15)   # compact — Streamlit scales width automatically

    fig = plt.figure(figsize=(13, fig_height))
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.99)

    gs = gridspec.GridSpec(
        n_panels, 1,
        height_ratios=height_ratios,
        hspace=0.06,
        left=0.08, right=0.97,
        top=0.94, bottom=0.08,
    )

    # Build axes dict
    axes: dict[str, object] = {}
    for i, (name, _) in enumerate(panels):
        if i == 0:
            axes[name] = fig.add_subplot(gs[i])
        else:
            axes[name] = fig.add_subplot(gs[i], sharex=axes[panels[0][0]])

    ax_equity: object = axes["equity"]

    # -----------------------------------------------------------------------
    # Panel: Equity curve
    # -----------------------------------------------------------------------
    ax_equity.plot(equity_curve.index, equity_curve.values,
                   color="#2196F3", linewidth=1.5, label="Strategy", zorder=3)

    if benchmark is not None:
        bm = benchmark.reindex(equity_curve.index, method="ffill")
        bm = bm / bm.dropna().iloc[0] * equity_curve.iloc[0]
        ax_equity.plot(bm.index, bm.values,
                       color="#9E9E9E", linewidth=1.0, linestyle="--",
                       label=benchmark_label, zorder=2, alpha=0.7)

    if show_equity_ma > 0:
        ma = equity_curve.rolling(show_equity_ma).mean()
        ax_equity.plot(ma.index, ma.values,
                       color="#FF9800", linewidth=1.2, linestyle="--",
                       label=f"MA({show_equity_ma})", zorder=4, alpha=0.9)

    if show_trades and trades:
        eq_index = equity_curve.index

        def _nearest_equity(t):
            """Return equity value at the closest timestamp."""
            idx = eq_index.searchsorted(pd.Timestamp(t))
            idx = min(idx, len(equity_curve) - 1)
            return float(equity_curve.iloc[idx])

        e_times  = [t.entry_time for t in trades]
        x_times  = [t.exit_time  for t in trades]
        e_eqs    = [_nearest_equity(t) for t in e_times]
        x_eqs    = [_nearest_equity(t) for t in x_times]
        x_colors = ["#4CAF50" if t.pnl > 0 else "#F44336" for t in trades]

        ax_equity.scatter(e_times, e_eqs, marker="^", s=35,
                          color="#1565C0", zorder=5, label="Entry", alpha=0.8)
        ax_equity.scatter(x_times, x_eqs, marker="v", s=35,
                          c=x_colors, zorder=5, label="Exit", alpha=0.8)

    if log_scale:
        ax_equity.set_yscale("log")
        ax_equity.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"${x:,.0f}")
        )
    else:
        ax_equity.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"${x:,.0f}")
        )

    ax_equity.set_ylabel("Capital ($)", fontsize=10)
    ax_equity.legend(fontsize=9, loc="upper left")
    ax_equity.grid(True, alpha=0.3)

    # Hide x tick labels on equity unless it is the last (only) panel
    last_data_panel = panels[-1][0] if panels[-1][0] != "metrics" else (panels[-2][0] if len(panels) > 1 else "equity")
    if panels[0][0] != last_data_panel:
        plt.setp(ax_equity.get_xticklabels(), visible=False)

    # -----------------------------------------------------------------------
    # Panel: Outperformance
    # -----------------------------------------------------------------------
    if "outperf" in axes and outperf_series is not None:
        ax_op = axes["outperf"]
        ax_op.fill_between(
            outperf_series.index, outperf_series.values, 0,
            where=(outperf_series.values >= 0),
            color="#4CAF50", alpha=0.3, interpolate=True,
        )
        ax_op.fill_between(
            outperf_series.index, outperf_series.values, 0,
            where=(outperf_series.values < 0),
            color="#F44336", alpha=0.3, interpolate=True,
        )
        ax_op.plot(outperf_series.index, outperf_series.values,
                   color="#1565C0", linewidth=0.9,
                   label=f"vs {benchmark_label}")
        ax_op.axhline(0, color="#9E9E9E", linewidth=0.8, linestyle="-")
        ax_op.set_ylabel("Outperf. (%)", fontsize=10)
        ax_op.legend(fontsize=8, loc="upper left")
        ax_op.grid(True, alpha=0.3)
        ax_op.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda x, _: f"{x:+.1f}%")
        )
        # Hide x-ticks unless bottom panel
        next_panels = [p[0] for p in panels[panels.index(("outperf", 1.2)) + 1:]]
        if any(p in next_panels for p in ("drawdown", "metrics")):
            plt.setp(ax_op.get_xticklabels(), visible=False)

    # -----------------------------------------------------------------------
    # Panel: Drawdown
    # -----------------------------------------------------------------------
    if "drawdown" in axes:
        ax_dd = axes["drawdown"]
        ax_dd.fill_between(drawdown.index, drawdown.values, 0,
                           color="#F44336", alpha=0.35, label="Drawdown")
        ax_dd.plot(drawdown.index, drawdown.values,
                   color="#F44336", linewidth=0.8)

        max_dd = float(drawdown.min())
        ax_dd.axhline(max_dd, color="#B71C1C", linewidth=0.8,
                      linestyle="--", label=f"Max DD: {max_dd:.1f}%")

        ax_dd.set_ylabel("Drawdown (%)", fontsize=10)
        ax_dd.legend(fontsize=8, loc="lower left")
        ax_dd.grid(True, alpha=0.3)

        # Format x-axis on this panel if it is not followed by a metrics bar,
        # or if it is the last panel overall
        is_last_visible = panels[-1][0] in ("drawdown", "metrics")
        if panels[-1][0] == "metrics":
            plt.setp(ax_dd.get_xticklabels(), visible=False)
        else:
            ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
            ax_dd.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            plt.setp(ax_dd.get_xticklabels(), rotation=30, ha="right", fontsize=8)

    # -----------------------------------------------------------------------
    # Ensure the bottom non-metrics panel has formatted x-axis
    # -----------------------------------------------------------------------
    # Find the lowest panel that is not "metrics"
    bottom_data_name = None
    for name, _ in reversed(panels):
        if name != "metrics":
            bottom_data_name = name
            break

    if bottom_data_name and bottom_data_name != "drawdown":
        ax_bottom = axes[bottom_data_name]
        ax_bottom.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax_bottom.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax_bottom.get_xticklabels(), rotation=30, ha="right", fontsize=8)
    elif bottom_data_name == "drawdown" and panels[-1][0] != "metrics":
        # Already handled above, but ensure formatting is applied
        ax_dd = axes["drawdown"]
        ax_dd.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax_dd.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax_dd.get_xticklabels(), rotation=30, ha="right", fontsize=8)

    # -----------------------------------------------------------------------
    # Panel: Compact metrics bar
    # -----------------------------------------------------------------------
    if "metrics" in axes:
        ax_metrics = axes["metrics"]
        ax_metrics.axis("off")
        m = metrics
        summary = (
            f"Return: {m.get('total_return_pct', 0):+.1f}%   "
            f"CAGR: {m.get('cagr_pct', 0):+.1f}%   "
            f"Sharpe: {m.get('sharpe_ratio', 0):.2f}   "
            f"Max DD: {m.get('max_drawdown_pct', 0):.1f}%   "
            f"Trades: {m.get('n_trades', 0)}   "
            f"Win rate: {m.get('win_rate_pct', 0):.0f}%   "
            f"Profit factor: {m.get('profit_factor', 0):.2f}"
        )
        ax_metrics.text(
            0.5, 0.5, summary,
            transform=ax_metrics.transAxes,
            ha="center", va="center", fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.4",
                      facecolor="#F5F5F5", edgecolor="#BDBDBD"),
        )

    # -----------------------------------------------------------------------
    # Save / show / return
    # -----------------------------------------------------------------------
    if save_path is not None:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Chart saved: {path}")

    if show:
        plt.show()
        plt.close(fig)
        return None

    # Return figure for embedding (Streamlit, notebooks, etc.)
    return fig
