"""
app.py — Streamlit GUI for the backtesting engine.

Launch: python -m streamlit run app.py
"""

from __future__ import annotations

import os
import sys
import importlib
import inspect
from datetime import datetime, date
from pathlib import Path
from typing import Optional

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from PIL import Image as _PILImage
_favicon = _PILImage.open(Path("assets/favicon.png")) if Path("assets/favicon.png").exists() else "📈"

st.set_page_config(
    page_title="Sextant — Backtest Engine",
    page_icon=_favicon,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-register standard derived series (once per session, not on every rerun)
if "derived_registered" not in st.session_state:
    try:
        from databank.derived import register_standard_derived
        register_standard_derived()
    except Exception:
        pass
    st.session_state["derived_registered"] = True

if "app_theme" not in st.session_state:
    st.session_state["app_theme"] = "light"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TECHNICAL_INDICATORS = [
    # ── Bar price fields — single bar, period disabled ───────────────────────
    ("RAW",             "CLOSE — close price",                1),   # "RAW" en interne pour compat
    ("OPEN",            "OPEN — open price",                  1),
    ("HIGH",            "HIGH — high of day",                 1),
    ("LOW",             "LOW — low of day",                   1),
    # ── Technical indicators ─────────────────────────────────────────────────
    ("RSI",             "RSI (0–100)",                       14),
    ("SMA",             "SMA — Simple moving average",       20),
    ("EMA",             "EMA — Exponential moving average",  20),
    ("ATR",             "ATR — Average True Range",          14),
    ("STOCH_K",         "Stochastic %K (0–100)",             14),
    ("MOMENTUM",        "Momentum",                          10),
    ("ROC",             "ROC — Rate of Change (%)",          10),
    ("BOLLINGER_UPPER", "Bollinger upper band",              20),
    ("BOLLINGER_MID",   "Bollinger middle band",             20),
    ("BOLLINGER_LOWER", "Bollinger lower band",              20),
    ("HIGHEST_HIGH",    "Highest high over N bars",          20),
    ("LOWEST_LOW",      "Lowest low over N bars",            20),
    ("VWAP",            "VWAP",                              20),
]

_BAR_FIELD_INDS = {"RAW", "OPEN", "HIGH", "LOW", "VOLUME"}  # period always = 1, input disabled

# Indicator list filtered for use on the CLOSE field (excludes bar-field shortcuts)
_CLOSE_IND_ENTRIES = [(n, l, p) for n, l, p in TECHNICAL_INDICATORS
                      if n not in ("OPEN", "HIGH", "LOW", "VOLUME")]
_CLOSE_IND_NAMES   = [t[0] for t in _CLOSE_IND_ENTRIES]
_CLOSE_IND_LABELS  = [t[1] for t in _CLOSE_IND_ENTRIES]

OPERATORS = [
    ("<",             "< (less than)"),
    (">",             "> (greater than)"),
    ("<=",            "<= (less than or equal)"),
    (">=",            ">= (greater than or equal)"),
    ("crosses_above", "crosses above"),
    ("crosses_below", "crosses below"),
]

NONE_WORDS = {"", "none", "no", "0", "off", "disable", "disabled"}


# ---------------------------------------------------------------------------
# Theme CSS injection
# ---------------------------------------------------------------------------

def _inject_css(theme: str):
    if theme == "dark":
        css = """
        <style>
        /* ── DARK THEME ─────────────────────────────────────── */
        .stApp, [data-testid="stAppViewContainer"] {
            background-color: #0D1117 !important;
        }
        [data-testid="stSidebar"] {
            background-color: #161B22 !important;
            border-right: 1px solid #30363D !important;
        }
        [data-testid="stSidebar"] * {
            color: #E6EDF3 !important;
        }
        h1 { color: #58A6FF !important; font-weight: 700; letter-spacing: -0.3px; }
        h2 { color: #79C0FF !important; font-weight: 600; }
        h3 { color: #A5D6FF !important; font-weight: 600; }
        p, label, .stMarkdown, div[data-testid="stText"] {
            color: #E6EDF3 !important;
        }
        /* Cards and containers */
        [data-testid="metric-container"] {
            background-color: #161B22 !important;
            border-radius: 8px !important;
            border: 1px solid #30363D !important;
            border-left: 4px solid #58A6FF !important;
            padding: 12px 16px !important;
            box-shadow: 0 2px 6px rgba(0,0,0,0.4) !important;
        }
        [data-testid="metric-container"] label {
            color: #8B949E !important;
            font-size: 0.78rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.6px !important;
        }
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: #E6EDF3 !important;
            font-weight: 700 !important;
        }
        /* Primary buttons — CTA */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #1565C0 0%, #1976D2 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 7px !important;
            font-weight: 600 !important;
            letter-spacing: 0.3px !important;
            padding: 0.45rem 1.2rem !important;
            transition: opacity 0.15s ease !important;
        }
        .stButton > button[kind="primary"]:hover {
            opacity: 0.88 !important;
        }
        /* Secondary buttons */
        .stButton > button:not([kind="primary"]) {
            border: 1.5px solid #30363D !important;
            color: #79C0FF !important;
            background: #161B22 !important;
            border-radius: 7px !important;
            font-weight: 500 !important;
        }
        .stButton > button:not([kind="primary"]):hover {
            border-color: #58A6FF !important;
            background: #1C2A3A !important;
        }
        /* Inputs */
        .stTextInput input, .stNumberInput input, textarea {
            background-color: #161B22 !important;
            color: #E6EDF3 !important;
            border: 1px solid #30363D !important;
            border-radius: 6px !important;
        }
        .stSelectbox > div > div {
            background-color: #161B22 !important;
            color: #E6EDF3 !important;
            border: 1px solid #30363D !important;
            border-radius: 6px !important;
        }
        /* Expanders */
        [data-testid="stExpander"] {
            border: 1px solid #30363D !important;
            border-radius: 8px !important;
            background-color: #161B22 !important;
        }
        /* Info / success / warning / error boxes */
        [data-testid="stAlert"] {
            border-radius: 7px !important;
        }
        /* Dividers */
        hr {
            border-color: #30363D !important;
            margin: 1.2rem 0 !important;
        }
        /* Dataframe */
        [data-testid="stDataFrame"] {
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        /* Tabs */
        [data-testid="stTabs"] [role="tab"] {
            color: #8B949E !important;
            font-weight: 500 !important;
        }
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            color: #58A6FF !important;
            border-bottom-color: #58A6FF !important;
        }
        /* Caption / small text */
        .stCaption, small {
            color: #8B949E !important;
        }
        /* Sidebar title */
        [data-testid="stSidebar"] h1 {
            color: #79C0FF !important;
            font-size: 1.15rem !important;
        }
        /* Code blocks */
        .stCode, code {
            background-color: #1C2128 !important;
            border: 1px solid #30363D !important;
            border-radius: 6px !important;
        }
        /* Remove any accidental border/background on column containers */
        [data-testid="column"] {
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
        }
        /* ── Global font size ───────────────────────────────────── */
        html, body, .stApp { font-size: 15.5px !important; }
        .stMarkdown p, div[data-testid="stMarkdownContainer"] p {
            font-size: 1.02rem !important;
        }
        div[data-testid="stAlert"] p { font-size: 1.0rem !important; }
        /* ── Larger form labels ─────────────────────────────────── */
        div[data-testid="stSelectbox"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stTextInput"] label,
        div[data-testid="stMultiSelect"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stCheckbox"] label,
        div[data-testid="stRadio"] label {
            font-size: 1.02rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.1px !important;
        }
        /* ── Button text ────────────────────────────────────────── */
        .stButton > button { font-size: 1.0rem !important; }
        /* ── Section subheaders ─────────────────────────────────── */
        div[data-testid="stHeadingWithActionElements"] h2,
        div[data-testid="stHeadingWithActionElements"] h3 {
            margin-top: 1.1rem !important;
            margin-bottom: 0.3rem !important;
        }
        /* ── Expander headings ──────────────────────────────────── */
        div[data-testid="stExpander"] summary {
            font-size: 1.02rem !important;
            font-weight: 600 !important;
        }
        /* ── Caption text ─────────────────────────────────────────── */
        div[data-testid="stCaptionContainer"] p { font-size: 0.88rem !important; }
        /* ── Metric values ───────────────────────────────────────── */
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
            font-weight: 700 !important;
        }
        </style>
        """
    else:  # light
        css = """
        <style>
        /* ── LIGHT THEME ────────────────────────────────────── */
        .stApp, [data-testid="stAppViewContainer"] {
            background-color: #F5F7FA !important;
        }
        [data-testid="stSidebar"] {
            background-color: #EBF0F8 !important;
            border-right: 1px solid #C5D5EA !important;
        }
        /* Headings */
        h1 {
            color: #1565C0 !important;
            font-weight: 700 !important;
            letter-spacing: -0.3px !important;
        }
        h2 {
            color: #1A237E !important;
            font-weight: 600 !important;
        }
        h3 {
            color: #283593 !important;
            font-weight: 600 !important;
        }
        /* Metric cards */
        [data-testid="metric-container"] {
            background-color: #FFFFFF !important;
            border-radius: 8px !important;
            border: 1px solid #DDEAF7 !important;
            border-left: 4px solid #1565C0 !important;
            padding: 12px 16px !important;
            box-shadow: 0 1px 4px rgba(21,101,192,0.08) !important;
        }
        [data-testid="metric-container"] label {
            color: #546E7A !important;
            font-size: 0.78rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.6px !important;
        }
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            color: #1A1A2E !important;
            font-weight: 700 !important;
        }
        /* Primary buttons — warm orange CTA */
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #E65100 0%, #FF8F00 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 7px !important;
            font-weight: 600 !important;
            letter-spacing: 0.3px !important;
            padding: 0.45rem 1.2rem !important;
            transition: opacity 0.15s ease !important;
        }
        .stButton > button[kind="primary"]:hover {
            opacity: 0.88 !important;
        }
        /* Secondary buttons — blue outline */
        .stButton > button:not([kind="primary"]) {
            border: 1.5px solid #1565C0 !important;
            color: #1565C0 !important;
            background: #FFFFFF !important;
            border-radius: 7px !important;
            font-weight: 500 !important;
        }
        .stButton > button:not([kind="primary"]):hover {
            background: #EBF0F8 !important;
        }
        /* Inputs */
        .stTextInput input, .stNumberInput input, textarea {
            background-color: #FFFFFF !important;
            border: 1px solid #C5D5EA !important;
            border-radius: 6px !important;
        }
        .stTextInput input:focus, .stNumberInput input:focus {
            border-color: #1565C0 !important;
            box-shadow: 0 0 0 2px rgba(21,101,192,0.12) !important;
        }
        /* Expanders */
        [data-testid="stExpander"] {
            border: 1px solid #DDEAF7 !important;
            border-radius: 8px !important;
            background-color: #FFFFFF !important;
        }
        /* Info / success / warning */
        [data-testid="stAlert"] {
            border-radius: 7px !important;
        }
        /* Dividers */
        hr {
            border-color: #DDEAF7 !important;
            margin: 1.2rem 0 !important;
        }
        /* Dataframe */
        [data-testid="stDataFrame"] {
            border-radius: 8px !important;
            overflow: hidden !important;
            border: 1px solid #DDEAF7 !important;
        }
        /* Tabs */
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
            color: #1565C0 !important;
            border-bottom-color: #1565C0 !important;
        }
        /* Caption */
        .stCaption, small {
            color: #546E7A !important;
        }
        /* Sidebar title */
        [data-testid="stSidebar"] h1 {
            color: #1565C0 !important;
        }
        /* Containers with border */
        [data-testid="stVerticalBlock"] > [data-testid="element-container"] > div[style*="border"] {
            border-color: #DDEAF7 !important;
            border-radius: 8px !important;
        }
        /* Remove any accidental border/background on column containers */
        [data-testid="column"] {
            border: none !important;
            box-shadow: none !important;
            background: transparent !important;
        }
        /* ── Global font size ───────────────────────────────────── */
        html, body, .stApp { font-size: 15.5px !important; }
        .stMarkdown p, div[data-testid="stMarkdownContainer"] p {
            font-size: 1.02rem !important;
        }
        div[data-testid="stAlert"] p { font-size: 1.0rem !important; }
        /* ── Larger form labels ─────────────────────────────────── */
        div[data-testid="stSelectbox"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stTextInput"] label,
        div[data-testid="stMultiSelect"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stCheckbox"] label,
        div[data-testid="stRadio"] label {
            font-size: 1.02rem !important;
            font-weight: 500 !important;
            letter-spacing: 0.1px !important;
        }
        /* ── Button text ────────────────────────────────────────── */
        .stButton > button { font-size: 1.0rem !important; }
        /* ── Section subheaders ─────────────────────────────────── */
        div[data-testid="stHeadingWithActionElements"] h2,
        div[data-testid="stHeadingWithActionElements"] h3 {
            margin-top: 1.1rem !important;
            margin-bottom: 0.3rem !important;
        }
        /* ── Expander headings ──────────────────────────────────── */
        div[data-testid="stExpander"] summary {
            font-size: 1.02rem !important;
            font-weight: 600 !important;
        }
        /* ── Caption text ─────────────────────────────────────────── */
        div[data-testid="stCaptionContainer"] p { font-size: 0.88rem !important; }
        /* ── Metric values ───────────────────────────────────────── */
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
            font-weight: 700 !important;
        }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


def _build_plotly_chart(
    equity_curve, trades, metrics, title,
    benchmark=None, benchmark_label="Benchmark",
    show_trades=True, show_drawdown=True, show_outperformance=False,
    show_equity_ma=0, log_scale=False, theme="light",
):
    """Interactive Plotly equity chart with optional drawdown and outperformance panels."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return None

    # ── Theme palette ────────────────────────────────────────────────────────
    if theme == "dark":
        bg, grid, txt = "#0D1117", "#30363D", "#E6EDF3"
        eq_c             = "#58A6FF"
        bm_c             = "#3FB950"
        dd_fill, dd_line = "rgba(248,81,73,0.25)", "#F85149"
        op_c_pos         = "#3FB950"
        op_c_neg         = "#F85149"
        op_fill_pos      = "rgba(63,185,80,0.28)"
        op_fill_neg      = "rgba(248,81,73,0.28)"
    else:
        bg, grid, txt = "#FFFFFF", "#E8EDF5", "#1A1A2E"
        eq_c             = "#1565C0"
        bm_c             = "#2E7D32"
        dd_fill, dd_line = "rgba(198,40,40,0.20)", "#C62828"
        op_c_pos         = "#2E7D32"
        op_c_neg         = "#C62828"
        op_fill_pos      = "rgba(46,125,50,0.25)"
        op_fill_neg      = "rgba(198,40,40,0.25)"

    # ── Pre-compute drawdown ─────────────────────────────────────────────────
    rolling_max = equity_curve.cummax()
    drawdown    = (equity_curve - rolling_max) / rolling_max * 100

    # ── Pre-compute benchmark (scaled) and outperformance ───────────────────
    bm_scaled      = None   # benchmark aligned & scaled to equity start
    outperf_series = None
    if benchmark is not None:
        _bm = benchmark.reindex(equity_curve.index, method="ffill").dropna()
        if not _bm.empty:
            bm_scaled = _bm / _bm.iloc[0] * equity_curve.iloc[0]
            if show_outperformance:
                _common = max(equity_curve.index[0], _bm.index[0])
                _eq_n   = equity_curve.loc[_common:] / equity_curve.loc[_common:].iloc[0]
                _bm_n   = _bm.loc[_common:] / _bm.loc[_common:].iloc[0]
                outperf_series = (_eq_n / _bm_n - 1) * 100

    _has_bm     = bm_scaled is not None
    _has_outperf = outperf_series is not None
    _has_dd      = show_drawdown

    # ── Subplot structure ────────────────────────────────────────────────────
    if _has_dd and _has_outperf:
        n_rows, row_heights, total_h = 3, [0.54, 0.23, 0.23], 1150
        dd_row, op_row = 2, 3
    elif _has_dd:
        n_rows, row_heights, total_h = 2, [0.68, 0.32], 950
        dd_row, op_row = 2, None
    elif _has_outperf:
        n_rows, row_heights, total_h = 2, [0.62, 0.38], 950
        dd_row, op_row = None, 2
    else:
        n_rows, row_heights, total_h = 1, [1.0], 700
        dd_row, op_row = None, None

    fig = make_subplots(
        rows=n_rows, cols=1,
        row_heights=row_heights,
        shared_xaxes=True,
        vertical_spacing=0.05,
    )

    # ── Equity curve ─────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=equity_curve.index, y=equity_curve.values,
        name="Portfolio",
        line=dict(color=eq_c, width=2.5),
        hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Equity: $%{y:,.0f}<extra></extra>",
    ), row=1, col=1)

    # ── Equity MA ────────────────────────────────────────────────────────────
    if show_equity_ma > 1:
        _ma = equity_curve.rolling(show_equity_ma).mean()
        fig.add_trace(go.Scatter(
            x=_ma.index, y=_ma.values,
            name=f"MA({show_equity_ma})",
            line=dict(color="#FFB74D", width=1.5, dash="dot"),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>MA: $%{y:,.0f}<extra></extra>",
        ), row=1, col=1)

    # ── Benchmark (scaled to equity start) ───────────────────────────────────
    if _has_bm:
        fig.add_trace(go.Scatter(
            x=bm_scaled.index, y=bm_scaled.values,
            name=benchmark_label,
            line=dict(color=bm_c, width=1.8, dash="dash"),
            opacity=0.85,
            hovertemplate=f"<b>%{{x|%Y-%m-%d}}</b><br>{benchmark_label}: $%{{y:,.0f}}<extra></extra>",
        ), row=1, col=1)

    # ── Trade markers ────────────────────────────────────────────────────────
    if show_trades and trades:
        el_x, el_y, el_t = [], [], []
        es_x, es_y, es_t = [], [], []
        ex_x, ex_y, ex_t = [], [], []
        for t in trades:
            try:
                _iy = min(equity_curve.index.searchsorted(t.entry_time, side="left"),
                          len(equity_curve) - 1)
                _ey = float(equity_curve.iloc[_iy])
            except Exception:
                continue
            _dir = getattr(t, "direction", None)
            _dv  = _dir.value if _dir and hasattr(_dir, "value") else str(_dir)
            if _dv == "LONG":
                el_x.append(t.entry_time); el_y.append(_ey)
                el_t.append(f"Entry LONG<br>@ ${t.entry_price:,.2f}")
            else:
                es_x.append(t.entry_time); es_y.append(_ey)
                es_t.append(f"Entry SHORT<br>@ ${t.entry_price:,.2f}")
            try:
                _xy = min(equity_curve.index.searchsorted(t.exit_time, side="left"),
                          len(equity_curve) - 1)
                _exy = float(equity_curve.iloc[_xy])
                _sgn = "+" if t.pnl >= 0 else ""
                ex_x.append(t.exit_time); ex_y.append(_exy)
                ex_t.append(f"Exit<br>@ ${t.exit_price:,.2f}<br>PnL: {_sgn}${t.pnl:,.0f}")
            except Exception:
                pass

        _mk = dict(line=dict(width=1, color="white"))
        if el_x:
            fig.add_trace(go.Scatter(
                x=el_x, y=el_y, mode="markers", name="Buy",
                marker=dict(symbol="triangle-up", size=11, color="#3FB950", **_mk),
                text=el_t, hovertemplate="%{text}<extra></extra>",
            ), row=1, col=1)
        if es_x:
            fig.add_trace(go.Scatter(
                x=es_x, y=es_y, mode="markers", name="Short",
                marker=dict(symbol="triangle-down", size=11, color="#F85149", **_mk),
                text=es_t, hovertemplate="%{text}<extra></extra>",
            ), row=1, col=1)
        if ex_x:
            fig.add_trace(go.Scatter(
                x=ex_x, y=ex_y, mode="markers", name="Exit",
                marker=dict(symbol="x", size=10, color="#FFB74D",
                            line=dict(width=2, color="#FFB74D")),
                text=ex_t, hovertemplate="%{text}<extra></extra>",
            ), row=1, col=1)

    # ── Drawdown panel ───────────────────────────────────────────────────────
    if _has_dd:
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown.values,
            name="Drawdown", fill="tozeroy",
            fillcolor=dd_fill, line=dict(color=dd_line, width=1),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>DD: %{y:.2f}%<extra></extra>",
        ), row=dd_row, col=1)

    # ── Outperformance panel ──────────────────────────────────────────────────
    if _has_outperf:
        _op_pos = outperf_series.clip(lower=0)
        _op_neg = outperf_series.clip(upper=0)
        fig.add_trace(go.Scatter(
            x=_op_pos.index, y=_op_pos.values,
            name="Alpha+", fill="tozeroy",
            fillcolor=op_fill_pos, line=dict(color=op_c_pos, width=1.5),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Alpha: +%{y:.2f}%<extra></extra>",
            showlegend=False,
        ), row=op_row, col=1)
        fig.add_trace(go.Scatter(
            x=_op_neg.index, y=_op_neg.values,
            name="Alpha-", fill="tozeroy",
            fillcolor=op_fill_neg, line=dict(color=op_c_neg, width=1.5),
            hovertemplate="<b>%{x|%Y-%m-%d}</b><br>Alpha: %{y:.2f}%<extra></extra>",
            showlegend=False,
        ), row=op_row, col=1)
        fig.add_hline(y=0, line=dict(color=grid, width=1, dash="dot"),
                      row=op_row, col=1)

    # ── Layout ───────────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color=txt)),
        paper_bgcolor=bg, plot_bgcolor=bg,
        font=dict(color=txt, size=12),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        height=total_h,
        margin=dict(l=70, r=20, t=55, b=20),
    )
    fig.update_xaxes(showgrid=True, gridcolor=grid, gridwidth=0.5, zeroline=False)
    fig.update_yaxes(
        showgrid=True, gridcolor=grid, gridwidth=0.5,
        tickprefix="$", tickformat=",.0f",
        type="log" if log_scale else "linear",
        row=1, col=1,
    )
    # Pas de range slider (il affiche toutes les traces en miniature → courbe fantôme)
    if _has_dd:
        fig.update_yaxes(
            ticksuffix="%", tickprefix="", title_text="DD",
            showgrid=True, gridcolor=grid, gridwidth=0.5,
            row=dd_row, col=1,
        )
    if _has_outperf:
        fig.update_yaxes(
            ticksuffix="%", tickprefix="",
            title_text=f"Alpha vs {benchmark_label}",
            showgrid=True, gridcolor=grid, gridwidth=0.5,
            row=op_row, col=1,
        )

    return fig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_pct(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str) and val.strip().lower() in NONE_WORDS:
        return None
    try:
        f = float(val)
        return None if f == 0 else f
    except (ValueError, TypeError):
        return None


def _fmt_pct(v) -> str:
    return f"{v*100:.1f}%" if v is not None else "none"


@st.cache_data(ttl=300, show_spinner=False)
def _list_tickers(tradeable_only=False) -> list[str]:
    try:
        from databank.catalog import list_assets
        assets = list_assets()
        if tradeable_only:
            # Exclude pure metric/indicator series (FRED etc.) — everything
            # else (equity, index, fx, crypto, future, other, …) is tradeable.
            non_tradeable = {"indicator", "macro"}
            assets = [e for e in assets if e.get("class") not in non_tradeable]
        return sorted(e["ticker"] for e in assets)
    except Exception:
        return []


@st.cache_data(ttl=30)
def _build_data_options(tradeable_only: bool = False) -> tuple[list[str], list[str]]:
    """
    Unified catalog picker: all assets sorted by provider / class / ticker.
    Returns (labels, tickers) — label is human-readable, ticker is the internal key.
    If tradeable_only=True, excludes pure indicator / macro series (FRED etc.).
    """
    try:
        from databank.catalog import list_assets
        assets = list_assets()
    except Exception:
        return [], []

    if tradeable_only:
        _non_tradeable = {"indicator", "macro"}
        assets = [e for e in assets if e.get("class") not in _non_tradeable]

    _cls_rank = {"equity": 0, "index": 1, "fx": 2, "crypto": 3, "indicator": 4, "other": 5}
    _prov_display = {
        "yfinance":    "YFinance",
        "fred":        "FRED",
        "tradingview": "TradingView",
    }

    def _sort_key(e):
        return (
            e.get("provider", "z").lower(),
            _cls_rank.get(e.get("class", "other"), 9),
            e.get("ticker", ""),
        )

    labels, tickers = [], []
    for e in sorted(assets, key=_sort_key):
        prov = _prov_display.get(e.get("provider", "").lower(),
                                 e.get("provider", "?").capitalize())
        cls    = e.get("class", "other")
        ticker = e["ticker"]
        name   = e.get("name", "")
        lbl = f"{prov} · {cls} · {ticker}"
        if name:
            lbl += f"  —  {name}"
        labels.append(lbl)
        tickers.append(ticker)

    return labels, tickers


def _series_latest_info(ticker: str) -> str:
    """Return a short formatted string with the latest close value of a metric series."""
    try:
        from databank.catalog import get as _cget
        from databank.normalizer import DataNormalizer
        _entry = _cget(ticker) or {}
        _unit  = _entry.get("currency", "")
        _df    = DataNormalizer().load_parquet(ticker, Path("DATASETS"))
        if _df is None or _df.empty:
            return ""
        _series = _df["close"].dropna()
        if _series.empty:
            return ""
        _lv   = _series.iloc[-1]
        _ldate = _series.index[-1].strftime("%Y-%m-%d")
        if _unit == "% (rate / yield)":
            _fmt = f"{_lv:.2f} %"
        elif _unit == "USD":
            _fmt = f"${_lv:,.2f}"
        elif _unit == "Index value":
            _fmt = f"{_lv:,.2f}"
        else:
            _fmt = f"{_lv:,.4f}"
        return f"Latest **{ticker}** = `{_fmt}` as of {_ldate}"
    except Exception:
        return ""


@st.cache_data(ttl=300, show_spinner=False)
def _list_strategies() -> list[str]:
    return sorted(
        p.stem for p in Path("strategies").glob("*.py")
        if not p.name.startswith("_")
    )


@st.cache_data(show_spinner=False)
def _load_run_summary(path_tuple: tuple) -> list[dict]:
    """Parse run JSON files; cached by file-path tuple (immutable once written)."""
    import json as _json_rs
    result = []
    for path_str in path_tuple:
        try:
            with open(path_str, encoding="utf-8") as _f:
                result.append(_json_rs.load(_f))
        except Exception:
            result.append({})
    return result


def _load_strategy_defaults(name: str) -> dict:
    try:
        import re
        from backtest.strategy.base import BaseStrategy
        if f"strategies.{name}" in sys.modules:
            del sys.modules[f"strategies.{name}"]
        mod = importlib.import_module(f"strategies.{name}")
        klass = next(
            (obj for _, obj in inspect.getmembers(mod, inspect.isclass)
             if issubclass(obj, BaseStrategy) and obj is not BaseStrategy),
            None,
        )
        if klass is None:
            return {}
        src = (Path("strategies") / f"{name}.py").read_text(encoding="utf-8", errors="replace")

        # symbols — prefer class attribute, fall back to file comment
        symbols_list = getattr(klass, "symbols", None) or []
        if not symbols_list:
            m = re.search(r"Assets?\s*:\s*([^\n]+)", src)
            if m:
                symbols_list = [s.strip().rstrip(",") for s in m.group(1).split(",") if s.strip()]
        symbol = symbols_list[0] if symbols_list else ""

        # Detect basket strategy (generated by generate_multi — no class-level position_size)
        is_basket = hasattr(klass, "_B1_ASSETS")

        if is_basket:
            # Collect basket summaries from class constants
            basket_summaries = []
            idx = 1
            while hasattr(klass, f"_B{idx}_ASSETS"):
                assets = getattr(klass, f"_B{idx}_ASSETS")
                sizes  = getattr(klass, f"_B{idx}_SIZES", {})
                sl     = getattr(klass, f"_B{idx}_SL",    None)
                tp     = getattr(klass, f"_B{idx}_TP",    None)
                basket_summaries.append({
                    "assets": list(assets),
                    "sizes":  sizes,
                    "sl":     sl,
                    "tp":     tp,
                })
                idx += 1
            return {
                "is_basket":      True,
                "symbols":        symbols_list,
                "symbol":         symbol,
                "execution_mode": getattr(klass, "execution_mode", "netting"),
                "basket_summaries": basket_summaries,
                # Provide fallback values so callers that read these keys don't crash
                "position_size":  None,
                "stop_loss":      None,
                "take_profit":    None,
            }

        return {
            "is_basket":      False,
            "position_size":  getattr(klass, "position_size",  0.10),
            "stop_loss":      getattr(klass, "stop_loss",      None),
            "take_profit":    getattr(klass, "take_profit",    None),
            "execution_mode": getattr(klass, "execution_mode", "netting"),
            "symbol":         symbol,
            "symbols":        symbols_list,
        }
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _load_benchmark(ticker: str, start_date, end_date) -> Optional["pd.Series"]:
    """Load close prices for a ticker from the data bank. Cached for 1 h."""
    try:
        import pandas as pd
        from databank.catalog import get as catalog_get
        entry = catalog_get(ticker)
        if entry:
            # Fast path: catalog tells us exactly which subfolder
            safe = ticker.replace("^", "_").replace("/", "_")
            path = Path("DATASETS") / entry["class"] / f"{safe}.parquet"
            if path.exists():
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                return df["close"].loc[str(start_date):str(end_date)]
        # Fallback: scan subdirs
        from databank.normalizer import DataNormalizer
        df = DataNormalizer().load_parquet(ticker, Path("DATASETS"))
        if df is None or df.empty:
            return None
        return df["close"].loc[str(start_date):str(end_date)]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

# ── Theme toggle ────────────────────────────────────────────────────────────
_theme_choice = st.sidebar.radio(
    "Theme",
    ["☀️  Light", "🌙  Dark"],
    index=0 if st.session_state["app_theme"] == "light" else 1,
    horizontal=True,
    key="theme_radio",
    label_visibility="collapsed",
)
st.session_state["app_theme"] = "light" if "Light" in _theme_choice else "dark"

# ── Inject CSS based on current theme ───────────────────────────────────────
_inject_css(st.session_state["app_theme"])

st.sidebar.markdown("---")
import base64 as _b64
def _svg_img(path: Path, width: str = "100%") -> str:
    """Return an <img> tag with base64-encoded SVG for st.markdown."""
    try:
        data = _b64.b64encode(path.read_bytes()).decode()
        return f'<img src="data:image/svg+xml;base64,{data}" width="{width}" style="display:block">'
    except Exception:
        return ""

_sb_icon_svg = Path("assets/logo_icon.svg")
if _sb_icon_svg.exists():
    st.sidebar.markdown(_svg_img(_sb_icon_svg, width="52"), unsafe_allow_html=True)
st.sidebar.markdown("### Sextant")
st.sidebar.markdown("---")
# Resolve pending navigation before the radio is instantiated
_PAGE_OPTIONS = ["🏠 Home", "🚀 Run Backtest", "🛠️ Build Strategy", "🔍 Review Strategy", "🗄️ Data Bank", "📊 Results"]
if "_nav_to" in st.session_state:
    _nt = st.session_state.pop("_nav_to")
    if _nt in _PAGE_OPTIONS:
        st.session_state["page_radio"] = _nt

page = st.sidebar.radio(
    "Navigation",
    _PAGE_OPTIONS,
    label_visibility="collapsed",
    key="page_radio",
)
st.sidebar.markdown("---")
st.sidebar.caption("Sextant v1.0  ·  `streamlit run app.py`")


# ===========================================================================
# PAGE: HOME
# ===========================================================================

if page == "🏠 Home":

    # ── Title / Logo ──────────────────────────────────────────────────────────
    _banner_svg = Path("assets/logo_banner.svg")
    if _banner_svg.exists():
        _logo_col, _ = st.columns([2, 3])
        with _logo_col:
            st.markdown(_svg_img(_banner_svg, width="100%"), unsafe_allow_html=True)
    else:
        st.markdown(
            "<h1 style='margin-bottom:0'>📈 Sextant</h1>"
            "<p style='color:grey;font-size:1.05rem;margin-top:0.2rem'>"
            "Event-driven strategy backtester — select a section to get started."
            "</p>",
            unsafe_allow_html=True,
        )
    st.markdown("---")

    # ── Navigation cards ──────────────────────────────────────────────────────
    _HOME_PAGES = [
        (
            "🚀 Run Backtest",
            "Run a strategy on historical data and get an equity curve, "
            "trade log and full performance metrics instantly.",
        ),
        (
            "🛠️ Build Strategy",
            "Create or edit a strategy file with the visual block editor — "
            "no Python required.",
        ),
        (
            "🔍 Review Strategy",
            "Inspect an existing strategy: rules, parameters, risk settings "
            "and basket composition.",
        ),
        (
            "🗄️ Data Bank",
            "Import and manage market data from Yahoo Finance and FRED. "
            "Update series with one click.",
        ),
        (
            "📊 Results",
            "Browse, compare and export all past backtest runs. "
            "Full interactive charts and statistics.",
        ),
    ]

    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"] .home-card-btn button {
            height: 2.8rem;
            font-size: 0.95rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    _card_cols = st.columns(len(_HOME_PAGES), gap="medium")
    for _cc, (_pname, _pdesc) in zip(_card_cols, _HOME_PAGES):
        with _cc:
            _icon, _label = _pname.split(" ", 1)
            st.markdown(
                f"<div style='text-align:center;font-size:2.4rem;line-height:1;margin-bottom:0.3rem'>{_icon}</div>"
                f"<div style='text-align:center;font-weight:700;font-size:1rem;margin-bottom:0.4rem'>{_label}</div>"
                f"<div style='text-align:center;font-size:0.8rem;color:grey;min-height:3.5rem'>{_pdesc}</div>",
                unsafe_allow_html=True,
            )
            with st.container():
                st.markdown('<div class="home-card-btn">', unsafe_allow_html=True)
                if st.button("Open →", key=f"home_nav_{_label}", use_container_width=True, type="primary"):
                    st.session_state["_nav_to"] = _pname
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── System status ─────────────────────────────────────────────────────────
    st.subheader("🔧 System status")

    # Compute once per session; invalidated by a manual Refresh button below
    if "_home_status" not in st.session_state:
        _hs: dict = {}
        try:
            import yfinance as _yf_home
            _hs["yf_ver"] = getattr(_yf_home, "__version__", "?")
            _hs["yf_ok"] = True
        except ImportError:
            _hs["yf_ok"] = False
        try:
            from databank.fred_config import get_api_key as _gk_home, is_configured as _ic_home
            if _ic_home():
                _hs["fred_key"] = (_gk_home() or "")[:4]
                _hs["fred_ok"] = True
            else:
                _hs["fred_ok"] = None        # not configured
        except Exception:
            _hs["fred_ok"] = False
        st.session_state["_home_status"] = _hs
    _hs = st.session_state["_home_status"]

    _st1, _st2, _st3, _st4 = st.columns(4, gap="medium")

    # yfinance
    with _st1:
        if _hs.get("yf_ok"):
            st.success(f"**Yahoo Finance**  \nyfinance v{_hs['yf_ver']} ✓", icon="✅")
        else:
            st.error("**Yahoo Finance**  \nyfinance not installed  \n`pip install yfinance`", icon="❌")

    # FRED API key
    with _st2:
        if _hs.get("fred_ok") is True:
            st.success(f"**FRED API**  \nKey saved (`{_hs['fred_key']}…`) ✓", icon="✅")
        elif _hs.get("fred_ok") is None:
            st.warning("**FRED API**  \nNo key set — FRED disabled  \nConfigure in Data Bank", icon="⚠️")
        else:
            st.warning("**FRED API**  \nModule unavailable", icon="⚠️")

    # Data bank
    with _st3:
        _all_h = _list_tickers()
        _trd_h = _list_tickers(tradeable_only=True)
        if _all_h:
            _ind_h = len(_all_h) - len(_trd_h)
            _detail = f"{len(_trd_h)} tradeable" + (f", {_ind_h} indicators" if _ind_h else "")
            st.success(f"**Data Bank**  \n{len(_all_h)} series ({_detail})", icon="✅")
        else:
            st.warning("**Data Bank**  \nNo data imported yet  \nGo to Data Bank", icon="⚠️")

    # Strategies
    with _st4:
        _strats_h = _list_strategies()
        if _strats_h:
            st.success(f"**Strategies**  \n{len(_strats_h)} available", icon="✅")
        else:
            st.warning("**Strategies**  \nNo strategies found  \nCreate one in Build Strategy", icon="⚠️")

    st.markdown("---")

    # ── Recent runs ────────────────────────────────────────────────────────────
    st.subheader("🕓 Recent runs")
    _home_run_files = sorted(
        (p for p in Path("logs").glob("*.json") if not p.name.endswith("_audit.json")),
        reverse=True,
    )[:5]

    if not _home_run_files:
        st.info("No runs yet — head to **🚀 Run Backtest** to launch your first backtest.")
    else:
        _path_tuple = tuple(str(p) for p in _home_run_files)
        _run_summaries = _load_run_summary(_path_tuple)

        # Header row
        _hc0, _hc1, _hc2, _hc3, _hc4, _hc5 = st.columns([4, 1.2, 1.1, 1.1, 1.1, 1.0])
        _hc0.markdown("**Run**")
        _hc1.markdown("**Date**")
        _hc2.markdown("**Return**")
        _hc3.markdown("**Sharpe**")
        _hc4.markdown("**Max DD**")
        _hc5.markdown("**Trades**")
        st.markdown(
            "<hr style='margin:0.3rem 0 0.5rem 0;border:none;border-top:1px solid #ddd'>",
            unsafe_allow_html=True,
        )
        for _rp, _rm in zip(_home_run_files, _run_summaries):
            try:
                _met      = _rm.get("metrics", {})
                _ret_v    = _met.get("total_return")
                _sr_v     = _met.get("sharpe")
                _dd_v     = _met.get("max_drawdown")
                _nt_v     = _met.get("num_trades")
                _ret_s    = f"{_ret_v*100:+.1f}%" if isinstance(_ret_v, (int, float)) else "—"
                _sr_s     = f"{_sr_v:.2f}"        if isinstance(_sr_v,  (int, float)) else "—"
                _dd_s     = f"{abs(_dd_v)*100:.1f}%" if isinstance(_dd_v, (int, float)) else "—"
                _nt_s     = str(int(_nt_v))        if isinstance(_nt_v,  (int, float)) else "—"
                _ret_col  = "green" if isinstance(_ret_v, (int, float)) and _ret_v >= 0 else "red"
                _rc0, _rc1, _rc2, _rc3, _rc4, _rc5 = st.columns([4, 1.2, 1.1, 1.1, 1.1, 1.0])
                _rc0.markdown(f"**{_rm.get('title', _rp.stem)}**")
                _rc1.markdown(
                    f"<span style='color:grey;font-size:0.85rem'>{_rm.get('saved_at','')[:10]}</span>",
                    unsafe_allow_html=True,
                )
                _rc2.markdown(
                    f"<span style='color:{_ret_col};font-weight:600'>{_ret_s}</span>",
                    unsafe_allow_html=True,
                )
                _rc3.markdown(_sr_s)
                _rc4.markdown(_dd_s)
                _rc5.markdown(_nt_s)
            except Exception:
                pass
        st.markdown(
            "<div style='text-align:right;margin-top:0.5rem'>"
            "</div>",
            unsafe_allow_html=True,
        )
        _home_results_c = st.columns([6, 2])
        with _home_results_c[1]:
            if st.button("📊  See all results →", use_container_width=True, key="home_goto_results"):
                st.session_state["_nav_to"] = "📊 Results"
                st.rerun()


# ===========================================================================
# PAGE: RUN BACKTEST
# ===========================================================================

elif page == "🚀 Run Backtest":
    # Clear any cached result when arriving from another page
    if st.session_state.get("_prev_page") != "🚀 Run Backtest":
        st.session_state.pop("last_result", None)
    st.session_state["_prev_page"] = "🚀 Run Backtest"

    st.title("🚀 Run Backtest")

    strategies = _list_strategies()
    tradeable  = _list_tickers(tradeable_only=True) or _list_tickers()

    if not strategies:
        st.error("No strategies found in `strategies/`. Create one first.")
        st.stop()
    if not tradeable:
        st.error("Data bank is empty. Import data via the Data Bank page.")
        st.stop()

    col1, _gap_col, col2 = st.columns([10, 1, 11])

    with col1:
        st.subheader("Strategy & Asset")
        strategy_name = st.selectbox("Strategy", strategies)

        defs = _load_strategy_defaults(strategy_name)
        _strat_symbols = defs.get("symbols") or ([defs.get("symbol")] if defs.get("symbol") else [])
        _is_basket = defs.get("is_basket", False)

        if _is_basket:
            # Basket strategy — assets fixed by the strategy
            selected_symbols = [s for s in _strat_symbols if s in tradeable]
            st.caption("**Assets to trade**")
            st.info("  ·  ".join(selected_symbols) if selected_symbols else "—", icon="📦")
        else:
            default_symbols  = [s for s in _strat_symbols if s in tradeable]
            selected_symbols = st.multiselect(
                "Asset(s) to trade", tradeable,
                default=default_symbols, key="rb_symbols"
            )
        symbol = selected_symbols[0] if selected_symbols else ""

        st.subheader("Period")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            _today = date.today()
            start_date = st.date_input("Start date",
                                       value=_today.replace(year=_today.year - 1),
                                       min_value=date(1900, 1, 1),
                                       max_value=_today)
        with col_d2:
            end_date = st.date_input("End date",
                                     value=_today,
                                     min_value=date(1900, 1, 1),
                                     max_value=_today)
        warmup_days = st.number_input(
            "Warmup period (calendar days)",
            min_value=0, max_value=365, value=0, step=10,
            help=(
                "**0** — data loads from Start date (no warmup).\n\n"
                "**N > 0** — data loads N calendar days *before* Start date so "
                "indicators (EMA, STOCH, RSI…) are fully initialised by the first bar. "
                "Trades are only recorded from Start date onward.\n\n"
                "*Rule of thumb: period × 1.5 ≈ trading bars. "
                "E.g. 90 days ≈ 60 trading bars — enough for EMA(21) or RSI(14).*"
            ),
        )

        capital = st.number_input(
            "Initial capital ($)", value=100_000, step=10_000, min_value=1_000
        )

    with col2:
        st.subheader("Risk parameters")

        if _is_basket:
            # Risk params baked into the strategy per-basket — show a summary
            st.info("Risk parameters are defined per-basket.", icon="ℹ️")
            _basket_rows = []
            for _bi, _bs in enumerate(defs.get("basket_summaries", []), 1):
                _b_assets = _bs["assets"]
                _b_sizes  = _bs["sizes"]
                _b_sl     = _bs["sl"]
                _b_tp     = _bs["tp"]
                _sz_parts = " · ".join(
                    f"{a} {round(v*100,1)}%" for a, v in _b_sizes.items()
                )
                _sl_str = f"{_b_sl*100:.1f}%" if _b_sl else "—"
                _tp_str = f"{_b_tp*100:.1f}%" if _b_tp else "—"
                _basket_rows.append({
                    "Basket": f"#{_bi}  ({', '.join(_b_assets)})",
                    "Allocation": _sz_parts,
                    "Stop loss": _sl_str,
                    "Take profit": _tp_str,
                })
            if _basket_rows:
                import pandas as _pd_tmp
                st.dataframe(
                    _pd_tmp.DataFrame(_basket_rows).set_index("Basket"),
                    use_container_width=True,
                )
            position_size = 0.10   # unused for basket strategies
            stop_loss     = None
            take_profit   = None

        else:
            # Read-only display — edit values in Build Strategy
            position_size = float(defs.get("position_size", 0.10))
            stop_loss     = defs.get("stop_loss")
            take_profit   = defs.get("take_profit")

            _rc1, _rc2, _rc3 = st.columns(3)
            _rc1.metric("Position size", f"{position_size * 100:.0f}%")
            _rc2.metric("Stop loss",     f"{stop_loss * 100:.1f}%"   if stop_loss   else "—")
            _rc3.metric("Take profit",   f"{take_profit * 100:.1f}%" if take_profit else "—")
            st.caption("ℹ️ Edit the strategy file to modify these values.")

        st.divider()
        _comm_pct = st.number_input(
            "Commission (%)",
            min_value=0.0, max_value=5.0,
            value=0.1, step=0.05, format="%.3f",
            help="Per-side commission, e.g. 0.1 = 0.1%",
        )
        commission = _comm_pct / 100

        st.subheader("Execution mode")
        _EXEC_LABELS = {
            "Netting — same-bar reversal (default)":
                "netting",
            "Netting — next-bar reversal (1-bar delay when reversing direction)":
                "netting_delay",
            "Hedge — LONG and SHORT can coexist on the same asset":
                "hedge",
        }
        _exec_default = defs.get("execution_mode", "netting")
        _exec_keys    = list(_EXEC_LABELS.values())
        _exec_idx     = _exec_keys.index(_exec_default) if _exec_default in _exec_keys else 0

        if _is_basket:
            # Execution mode is baked into the strategy — show but don't allow override
            _exec_display = {
                "netting":       "🟡 Netting — same-bar reversal",
                "netting_delay": "🟡 Netting — next-bar reversal",
                "hedge":         "🔵 Hedge — LONG & SHORT coexist",
            }
            st.caption(f"Mode (from strategy): **{_exec_display.get(_exec_default, _exec_default)}**")
            exec_mode_str = _exec_default
        else:
            exec_label = st.selectbox(
                "Mode",
                list(_EXEC_LABELS.keys()),
                index=_exec_idx,
                key="exec_mode",
                help=(
                    "**Netting same-bar**: one position per asset; "
                    "reversing SHORT→LONG (or vice-versa) closes and reopens atomically.\n\n"
                    "**Netting next-bar**: same but the new position opens the following bar.\n\n"
                    "**Hedge**: a LONG and a SHORT can be open simultaneously (delta-neutral strategies)."
                ),
            )
            exec_mode_str = _EXEC_LABELS[exec_label]

    st.markdown("---")
    run_btn = st.button("▶  Run backtest", type="primary", use_container_width=True)

    if run_btn:
        with st.spinner("Computing…"):
            try:
                from backtest.core.queue import EventQueue
                from backtest.data.handler import DataBankHandler
                from backtest.engine import BacktestEngine
                from backtest.execution.simulated import CommissionConfig, SimulatedExecutionHandler
                from backtest.portfolio.base import SimplePortfolio
                from backtest.risk.rules import ExecutionMode, StandardRiskManager
                from backtest.strategy.base import BaseStrategy

                # Force-reload the strategy module to avoid stale state between runs
                for _k in list(sys.modules.keys()):
                    if _k == f"strategies.{strategy_name}" or _k.startswith(f"strategies.{strategy_name}."):
                        del sys.modules[_k]
                mod = importlib.import_module(f"strategies.{strategy_name}")
                klass = next(
                    (obj for _, obj in inspect.getmembers(mod, inspect.isclass)
                     if issubclass(obj, BaseStrategy) and obj is not BaseStrategy),
                    None,
                )
                if klass is None:
                    st.error("No BaseStrategy subclass found in this strategy file.")
                    st.stop()

                run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                queue  = EventQueue()
                _syms  = selected_symbols if selected_symbols else [symbol]

                # Refresh any derived series (breadth indicators, etc.)
                try:
                    from databank.derived import DerivedSeriesManager
                    _dm   = DerivedSeriesManager()
                    _defs = _dm._load_defs()
                    for _s in _syms:
                        if _s.upper() in _defs:
                            _dm.compute(name=_s.upper())
                except Exception:
                    pass

                from datetime import timedelta as _td
                _trade_start_dt = datetime.combine(start_date, datetime.min.time())
                _warmup_start   = (start_date - _td(days=int(warmup_days))) if warmup_days > 0 else start_date
                _load_start_dt  = datetime.combine(_warmup_start, datetime.min.time())

                data = DataBankHandler(
                    symbols=_syms, queue=queue,
                    market_data_dir=Path("DATASETS"),
                    start_date=_load_start_dt,
                    end_date=datetime.combine(end_date, datetime.min.time()),
                )

                strategy = klass(data=data, queue=queue)
                if not _is_basket:
                    strategy.position_size = position_size
                    strategy.stop_loss     = stop_loss
                    strategy.take_profit   = take_profit

                portfolio = SimplePortfolio(initial_capital=float(capital), data=data,
                                            execution_mode=exec_mode_str)
                risk      = StandardRiskManager(
                    execution_mode=ExecutionMode(exec_mode_str)
                )
                execution = SimulatedExecutionHandler(
                    data=data, queue=queue,
                    commission=CommissionConfig(rate=commission),
                )
                engine = BacktestEngine(
                    data=data, strategies=[strategy], portfolio=portfolio,
                    risk=risk, execution=execution, queue=queue,
                    initial_capital=float(capital),
                    log_dir=Path("logs"), run_id=run_id,
                    trade_start_date=_trade_start_dt if warmup_days > 0 else None,
                )
                result = engine.run()
                n_bars = data._cursor   # bars processed

                # Save run data as JSON for interactive replay in Results page
                try:
                    import json as _json
                    from datetime import datetime as _dt
                    def _to_jsonable(v):
                        if hasattr(v, "item"):   return v.item()   # numpy scalar
                        if hasattr(v, "isoformat"): return v.isoformat()
                        try: return float(v)
                        except Exception: return str(v)
                    _run_title = (
                        f"{strategy_name} — {', '.join(_syms)}  ({start_date} → {end_date})"
                        + (f"  [warmup: {warmup_days}d]" if warmup_days > 0 else "")
                    )
                    _run_data = {
                        "title":    _run_title,
                        "run_id":   run_id,
                        "saved_at": _dt.now().isoformat(),
                        "equity_curve": {
                            "index":  [str(ts) for ts in result.equity_curve.index],
                            "values": [float(v) for v in result.equity_curve.values],
                        },
                        "trades":  [t.to_dict() for t in result.trades],
                        "metrics": {k: _to_jsonable(v) for k, v in result.metrics.items()},
                    }
                    _json_path = Path("logs") / f"{run_id}.json"
                    _json_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(_json_path, "w", encoding="utf-8") as _jf:
                        _json.dump(_run_data, _jf, default=str)
                except Exception:
                    pass

            except FileNotFoundError as e:
                st.error(f"Data file not found: {e}")
                st.stop()
            except ValueError as e:
                st.error(f"Configuration error: {e}")
                st.stop()
            except Exception as e:
                import traceback
                st.error(f"Error: {e}")
                st.code(traceback.format_exc())
                st.stop()

        # Store result in session state so chart options can re-render without re-running
        # Also invalidate the Home "recent runs" cache (new file appeared on disk)
        _load_run_summary.clear()
        st.session_state["last_result"] = {
            "equity_curve": result.equity_curve,
            "trades":       result.trades,
            "metrics":      result.metrics,
            "title":        (
                f"{strategy_name} — {', '.join(_syms)}  ({start_date} → {end_date})"
                + (f"  [warmup: {warmup_days}d]" if warmup_days > 0 else "")
            ),
            "start_date":   start_date,
            "end_date":     end_date,
            "run_id":       run_id,
            "symbol":       symbol,
            "n_bars":       n_bars,
            "is_basket":    _is_basket,
        }

        # ── Metric cards ─────────────────────────────────────────────────────
        _n_trades  = len(result.trades)
        _eq_final  = result.equity_curve.iloc[-1] if not result.equity_curve.empty else float(capital)
        _bars_label = (
            f"**{n_bars:,} bars** processed ({warmup_days}d warmup)"
            if warmup_days > 0 else f"**{n_bars:,} bars** processed"
        )
        st.success(
            f"Done — {_bars_label} · **{_n_trades} trades** · "
            f"final equity **${_eq_final:,.0f}**"
        )
        m = result.metrics

        # Color-aware metric borders
        _ret = m.get('total_return_pct', 0)
        _mdd = m.get('max_drawdown_pct', 0)
        _sharpe = m.get('sharpe_ratio', 0)
        _win_rate = m.get('win_rate_pct', 0)
        _pf = m.get('profit_factor', 0)

        def _border_color(val, positive_good=True, theme="light"):
            _pos = "#2E7D32" if theme == "light" else "#3FB950"
            _neg = "#C62828" if theme == "light" else "#F85149"
            _neu = "#1565C0" if theme == "light" else "#58A6FF"
            if val > 0 and positive_good: return _pos
            if val < 0 and positive_good: return _neg
            return _neu

        _th = st.session_state.get("app_theme", "light")
        _metric_css = f"""
<style>
/* Metric card border colors - post-run */
section.main div[data-testid="metric-container"]:nth-child(1) {{ border-left-color: {"#2E7D32" if _eq_final > float(capital) else "#C62828" if _th == "light" else ("#3FB950" if _eq_final > float(capital) else "#F85149")} !important; }}
section.main div[data-testid="metric-container"]:nth-child(2) {{ border-left-color: {_border_color(_ret, True, _th)} !important; }}
section.main div[data-testid="metric-container"]:nth-child(4) {{ border-left-color: {_border_color(_sharpe, True, _th)} !important; }}
section.main div[data-testid="metric-container"]:nth-child(5) {{ border-left-color: {_border_color(-_mdd, True, _th)} !important; }}
</style>
"""
        st.markdown(_metric_css, unsafe_allow_html=True)

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Final capital",      f"${_eq_final:,.0f}")
        c2.metric("Total return",       f"{m.get('total_return_pct', 0):+.1f}%")
        c3.metric("CAGR",               f"{m.get('cagr_pct', 0):+.1f}%")
        c4.metric("Sharpe ratio",       f"{m.get('sharpe_ratio', 0):.2f}")
        c5.metric("Max drawdown",       f"{m.get('max_drawdown_pct', 0):.1f}%")
        c6.metric("Trades",             str(m.get("n_trades", 0)))
        c7, c8, c9, c10, c11, c12 = st.columns(6)
        c7.metric("Win rate",           f"{m.get('win_rate_pct', 0):.0f}%")
        c8.metric("Profit factor",      f"{m.get('profit_factor', 0):.2f}")
        c9.metric("Avg win",            f"{m.get('avg_win_pct', 0):+.2f}%")
        c10.metric("Avg loss",          f"{m.get('avg_loss_pct', 0):+.2f}%")
        c11.metric("Stop loss exits",   str(m.get("n_stop_loss", 0)))
        c12.metric("Take profit exits", str(m.get("n_take_profit", 0)))
        st.caption("📊 Full ratios (Sortino, Calmar, drawdown duration, commissions…) available in the **Results** page.")

    # -----------------------------------------------------------------------
    # Chart + options + trades — rendered whenever a result exists.
    # Changing any chart option rerenders without re-running the backtest.
    # -----------------------------------------------------------------------
    if "last_result" in st.session_state:
        import pandas as pd

        lr = st.session_state["last_result"]

        st.markdown("---")

        # ── Chart options ────────────────────────────────────────────────────
        bench_options = _list_tickers(tradeable_only=True) or _list_tickers()
        # Ligne 1 : Benchmark + MA
        _oa, _ob, _oc = st.columns([3, 1, 2])
        with _oa:
            bench_ticker = st.selectbox(
                "Benchmark", ["None"] + bench_options, key="bench_ticker",
            )
        with _ob:
            eq_ma = st.number_input(
                "Equity MA", min_value=0, max_value=200, value=0,
                step=5, key="eq_ma", help="Overlay a rolling moving average on the equity curve (0 = off)",
            )
        # Ligne 2 : checkboxes
        _cb1, _cb2, _cb3, _cb4, _cb5 = st.columns(5)
        with _cb1:
            show_outperf = st.checkbox(
                "Outperformance", value=True, key="show_outperf",
                disabled=(bench_ticker == "None"),
            )
        with _cb2:
            show_trades_cb = st.checkbox("Trade markers", value=True, key="show_trades_cb")
        with _cb3:
            show_drawdown_cb = st.checkbox("Drawdown", value=True, key="show_drawdown_cb")
        with _cb4:
            log_scale_cb = st.checkbox("Log scale", value=False, key="log_scale_cb")

        # ── Load benchmark ───────────────────────────────────────────────────
        bench_series = None
        if bench_ticker != "None":
            with st.spinner(f"Loading {bench_ticker}…"):
                bench_series = _load_benchmark(bench_ticker, lr["start_date"], lr["end_date"])
            if bench_series is None:
                st.warning(f"Could not load benchmark data for {bench_ticker}.")

        # ── Interactive Plotly chart (zoom, hover, range slider) ─────────────
        _pf = _build_plotly_chart(
            equity_curve=lr["equity_curve"],
            trades=lr.get("trades", []),
            metrics=lr.get("metrics", {}),
            title=lr["title"],
            benchmark=bench_series,
            benchmark_label=bench_ticker if bench_ticker != "None" else "Benchmark",
            show_trades=show_trades_cb,
            show_drawdown=show_drawdown_cb,
            show_outperformance=show_outperf and bench_series is not None,
            show_equity_ma=int(eq_ma),
            log_scale=log_scale_cb,
            theme=st.session_state.get("app_theme", "light"),
        )
        if _pf is not None:
            _chart_key = (
                f"main_{bench_ticker}_{int(show_outperf)}_{int(show_drawdown_cb)}"
                f"_{int(show_trades_cb)}_{int(log_scale_cb)}_{eq_ma}"
            )
            st.plotly_chart(_pf, use_container_width=True, key=_chart_key)

        # ── Trade table ──────────────────────────────────────────────────────
        trades = lr.get("trades", [])
        if trades:
            st.markdown("---")
            _n_eob = sum(1 for t in trades if getattr(t, "exit_reason", "") == "end_of_backtest")
            _n_sig = len(trades) - _n_eob
            _header = f"Trades — {_n_sig} closed by signal"
            if _n_eob:
                _header += f", {_n_eob} force-closed at end of period"
            st.subheader(_header)
            st.caption(
                "ℹ️ The equity curve reflects open positions mark-to-market. "
                "A trade appears here only once it is **closed**. "
                "Positions still open at the backtest end-date are force-closed "
                "and shown with exit reason **end_of_backtest**."
            )

            _multi_sym  = len({t.symbol for t in trades}) > 1
            _has_basket = any(getattr(t, "basket_id", None) for t in trades)

            rows = []
            for t in trades:
                r = {}
                if _multi_sym:
                    r["Symbol"] = t.symbol
                if _has_basket:
                    r["Basket"] = getattr(t, "basket_id", None) or "—"
                r["Entry"]       = str(t.entry_time.date())
                r["Exit"]        = str(t.exit_time.date())
                r["Dir"]         = t.direction.value
                r["Entry $"]     = round(t.entry_price, 2)
                r["Exit $"]      = round(t.exit_price, 2)
                r["PnL ($)"]     = round(t.pnl, 2)
                r["PnL (%)"]     = f"{t.pnl_pct*100:+.2f}%"
                r["Exit reason"] = t.exit_reason
                rows.append(r)

            df_trades = pd.DataFrame(rows)

            def _color_pnl(val):
                if isinstance(val, str) and val.startswith("+"):
                    return "color: #2e7d32"
                if isinstance(val, str) and val.startswith("-"):
                    return "color: #c62828"
                return ""

            st.dataframe(
                df_trades.style.applymap(_color_pnl, subset=["PnL (%)"]),
                use_container_width=True, hide_index=True,
            )


# ===========================================================================
# PAGE: BUILD STRATEGY
# ===========================================================================

elif page == "🛠️ Build Strategy":
    st.markdown("""
    <style>
    div.builder-reset-btn button {
        background-color: #E65100 !important;
        color: white !important;
        border-color: #E65100 !important;
    }
    div.builder-reset-btn button:hover {
        background-color: #BF360C !important;
        border-color: #BF360C !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _bs_title_col, _bs_lbl_col, _bs_btn_col = st.columns([6, 2, 2])
    _bs_title_col.title("🛠️ Build a new strategy")
    with _bs_lbl_col:
        st.markdown(
            '<p style="margin:0;padding-top:1.55rem;text-align:right;'
            'font-size:0.9rem;color:rgba(49,51,63,0.7)">Reset settings :</p>',
            unsafe_allow_html=True,
        )
    with _bs_btn_col:
        st.markdown('<p style="margin:0 0 0.35rem 0;font-size:0.875rem;color:rgba(49,51,63,0.6)"> </p>', unsafe_allow_html=True)
        st.markdown('<div class="builder-reset-btn">', unsafe_allow_html=True)
        if st.button("✨ New strategy", key="builder_new_btn", use_container_width=True):
            st.session_state["_builder_reset_pending"] = True
            for _bk in ["entry_conds", "exit_conds", "short_entry_conds",
                        "cover_exit_conds", "baskets", "strategy_exec_mode"]:
                st.session_state.pop(_bk, None)
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Backward-compat session state (old single-basket keys) ──────────────
    if "entry_conds" not in st.session_state:
        st.session_state.entry_conds       = []
    if "exit_conds" not in st.session_state:
        st.session_state.exit_conds        = []
    if "short_entry_conds" not in st.session_state:
        st.session_state.short_entry_conds = []
    if "cover_exit_conds" not in st.session_state:
        st.session_state.cover_exit_conds  = []

    # ── Multi-basket session state ───────────────────────────────────────────
    if "baskets" not in st.session_state:
        st.session_state.baskets = [
            {
                "id":             "basket_1",
                "assets":         [],
                "weights":        {},
                "basket_size":       10.0,
                "basket_sl":         2.0,
                "basket_tp":         5.0,
                "use_custom_size":   False,
                "use_sl":            False,
                "use_tp":            False,
                "entry_conds":       [],
                "exit_conds":        [],
                "short_entry_conds": [],
                "cover_exit_conds":  [],
            }
        ]
    if "strategy_exec_mode" not in st.session_state:
        st.session_state.strategy_exec_mode = "netting"

    # ── Deferred reset after save ─────────────────────────────────────────────
    # Widget keys (strat_name_input, strat_desc_input, b{i}_* widgets) cannot
    # be set AFTER the widget has rendered. We use a flag set at save-time and
    # consumed here, BEFORE any widget is rendered, to safely clear those keys.
    if st.session_state.pop("_builder_reset_pending", False):
        for _k in ["strat_name_input", "strat_desc_input"]:
            st.session_state.pop(_k, None)
        for _k in list(st.session_state.keys()):
            if _k.startswith("b") and any(
                x in _k for x in ("_use_size", "_bsize", "_use_sl", "_sl",
                                  "_use_tp", "_tp", "_assets", "_w_")
            ):
                del st.session_state[_k]

    all_series = _list_tickers()
    # Tradeable assets — sorted + labelled exactly like the Data series picker
    _tr_labels, _tr_tickers = _build_data_options(tradeable_only=True)
    tradeable      = _tr_tickers or (_list_tickers(tradeable_only=True) or all_series)
    _tradeable_set = set(tradeable)
    _tr_lbl_map    = dict(zip(_tr_tickers, _tr_labels))   # ticker -> display label
    ind_series = [t for t in all_series if t not in _tradeable_set]
    ind_names  = [t[0] for t in TECHNICAL_INDICATORS]
    ind_labels = [f"{t[0]} — {t[1]}" for t in TECHNICAL_INDICATORS]
    op_keys    = [o[0] for o in OPERATORS]
    op_labels  = [o[1] for o in OPERATORS]

    # ---- Condition editor (reusable, takes explicit list key in session_state) ----
    def cond_editor(key_prefix: str, cond_list_key: str):
        # cond_list_key must be a top-level key in st.session_state
        conds = st.session_state[cond_list_key]

        if conds:
            for i, c in enumerate(conds):
                cols = st.columns([6, 1])
                prefix = "IF" if i == 0 else c.get("logic", "AND")
                with cols[0]:
                    st.markdown(f"**{prefix}** &nbsp; `{c['human']}`")
                with cols[1]:
                    if st.button("✕", key=f"{key_prefix}_del_{i}"):
                        conds.pop(i)
                        st.rerun()

        with st.expander("➕ Add a condition", expanded=len(conds) == 0,
                         key=f"{key_prefix}_add_exp"):
            logic = "AND"
            if conds:
                logic_sel = st.radio(
                    "Combine with previous condition:",
                    ["AND", "OR"], horizontal=True, key=f"{key_prefix}_logic"
                )
                logic = logic_sel

            # ── Unified data catalog ─────────────────────────────────────────
            _do_labels, _do_tickers = _build_data_options()

            # ── LEFT SIDE — 3 sequential choices ────────────────────────────
            c_left_type = "series_indicator"
            c_left_name = c_left_series = ""
            c_left_period = 1
            c_right_type = c_right_name = c_right_series = ""
            c_right_period = 0
            c_right_value  = 0.0
            c_op           = ""

            _lf_col, _ld_col = st.columns([1, 2])
            with _lf_col:
                ev_field = st.selectbox(
                    "① Evaluate — Field",
                    ["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"],
                    key=f"{key_prefix}_ev_field",
                )
            with _ld_col:
                if _do_labels:
                    _ev_lbl = st.selectbox(
                        "② Data series",
                        _do_labels,
                        key=f"{key_prefix}_ev_data",
                    )
                    c_left_series = _do_tickers[_do_labels.index(_ev_lbl)]
                    _lser_info = _series_latest_info(c_left_series)
                    if _lser_info:
                        st.caption(_lser_info)
                else:
                    st.warning("No data in the bank — import data first.")
                    c_left_series = ""

            if ev_field == "CLOSE":
                _li_col, _lp_col = st.columns([3, 1])
                with _li_col:
                    li = st.selectbox(
                        "③ Indicator",
                        _CLOSE_IND_LABELS,
                        key=f"{key_prefix}_ev_ind",
                    )
                    c_left_name = _CLOSE_IND_NAMES[_CLOSE_IND_LABELS.index(li)]
                with _lp_col:
                    _is_bar = c_left_name in _BAR_FIELD_INDS
                    dp = _CLOSE_IND_ENTRIES[_CLOSE_IND_LABELS.index(li)][2]
                    _prd = st.number_input(
                        "Period", min_value=1, value=dp,
                        key=f"{key_prefix}_ev_prd_{c_left_name}",
                        disabled=_is_bar,
                    )
                    c_left_period = 1 if _is_bar else int(_prd)
            else:
                # OPEN / HIGH / LOW / VOLUME — field IS the indicator, period always 1
                c_left_name   = ev_field
                c_left_period = 1

            op_label = st.selectbox("Operator", op_labels, key=f"{key_prefix}_op")
            c_op = op_keys[op_labels.index(op_label)]

            # ── RIGHT SIDE ───────────────────────────────────────────────────
            right_type_label = st.selectbox(
                "Compare with",
                ["Fixed value", "Another series"],
                key=f"{key_prefix}_rtype",
            )

            if right_type_label == "Fixed value":
                c_right_type = "value"
                c_right_value = st.number_input(
                    "Value", value=0.0, step=1.0,
                    format="%.4f", key=f"{key_prefix}_rval",
                )
            else:
                c_right_type = "series_indicator"
                _rf_col, _rd_col = st.columns([1, 2])
                with _rf_col:
                    rv_field = st.selectbox(
                        "① Field",
                        ["CLOSE", "OPEN", "HIGH", "LOW", "VOLUME"],
                        key=f"{key_prefix}_rv_field",
                    )
                with _rd_col:
                    if _do_labels:
                        _rv_lbl = st.selectbox(
                            "② Data series",
                            _do_labels,
                            key=f"{key_prefix}_rv_data",
                        )
                        c_right_series = _do_tickers[_do_labels.index(_rv_lbl)]
                        _rser_info = _series_latest_info(c_right_series)
                        if _rser_info:
                            st.caption(_rser_info)
                    else:
                        c_right_series = ""

                if rv_field == "CLOSE":
                    _ri_col, _rp_col = st.columns([3, 1])
                    with _ri_col:
                        ri = st.selectbox(
                            "③ Indicator",
                            _CLOSE_IND_LABELS,
                            key=f"{key_prefix}_rv_ind",
                        )
                        c_right_name = _CLOSE_IND_NAMES[_CLOSE_IND_LABELS.index(ri)]
                    with _rp_col:
                        _is_bar = c_right_name in _BAR_FIELD_INDS
                        dp = _CLOSE_IND_ENTRIES[_CLOSE_IND_LABELS.index(ri)][2]
                        _prd = st.number_input(
                            "Period", min_value=1, value=dp,
                            key=f"{key_prefix}_rv_prd_{c_right_name}",
                            disabled=_is_bar,
                        )
                        c_right_period = 1 if _is_bar else int(_prd)
                else:
                    c_right_name   = rv_field
                    c_right_period = 1

            # Human-readable preview
            def _slabel(typ, name, period, series, value):
                if typ == "series_indicator":
                    _disp = "CLOSE" if name == "RAW" else name
                    if name in _BAR_FIELD_INDS:
                        return f"{_disp} on {series}"
                    return f"{_disp}({period}) on {series}"
                if typ in ("series", "bar"):
                    return str(name)
                return str(value)

            h_left  = _slabel(c_left_type,  c_left_name,  c_left_period,  c_left_series,  None)
            h_right = _slabel(c_right_type, c_right_name, c_right_period, c_right_series, c_right_value)
            human   = f"{h_left}  {c_op}  {h_right}"

            # Timing options — deux paramètres indépendants et combinables
            _is_crossing = c_op in ("crosses_above", "crosses_below")

            # Live sanity check — shows current value and TRUE/FALSE for simple comparisons.
            # Works for:
            #   • RAW on any series (just reads last close)
            #   • Any indicator on tradable asset or metric series (computes live)
            _sanity_line = ""
            _is_simple_cmp = c_right_type == "value" and c_op not in ("crosses_above", "crosses_below")
            _is_ind_vs_ind = (
                c_right_type == "series_indicator" and c_right_series
                and c_left_type == "series_indicator" and c_left_series
                and c_op not in ("crosses_above", "crosses_below")
            )

            def _ind_fmt(name, val):
                if name in ("RSI", "STOCH_K"):
                    return f"{val:.1f}"
                if name in ("SMA", "EMA", "BOLLINGER_UPPER", "BOLLINGER_MID",
                            "BOLLINGER_LOWER", "VWAP", "HIGHEST_HIGH", "LOWEST_LOW"):
                    return f"{val:,.2f}"
                if name in ("ATR", "MOMENTUM"):
                    return f"{val:.4f}"
                if name == "ROC":
                    return f"{val:+.2f}%"
                return f"{val:,.4f}"

            if _is_simple_cmp and c_left_type == "series_indicator" and c_left_series:
                try:
                    from databank.normalizer import DataNormalizer as _DN3
                    from backtest.strategy.indicators import compute_indicator as _ci
                    _sdf2 = _DN3().load_parquet(c_left_series, Path("DATASETS"))
                    if _sdf2 is not None and not _sdf2.empty:
                        _extra = 2 if c_left_name in ("EMA", "BOLLINGER_UPPER", "BOLLINGER_MID",
                                                       "BOLLINGER_LOWER", "VWAP") else 1
                        _need  = c_left_period + _extra
                        _last_bars = _sdf2.tail(_need)
                        if len(_last_bars) >= _need:
                            _sv  = _ci(c_left_name, _last_bars, c_left_period)
                            _sd  = _last_bars.index[-1].strftime("%Y-%m-%d")
                            _sfmt = _ind_fmt(c_left_name, _sv)
                            _cmp = {
                                ">":  _sv > c_right_value,
                                ">=": _sv >= c_right_value,
                                "<":  _sv < c_right_value,
                                "<=": _sv <= c_right_value,
                            }
                            if c_op in _cmp:
                                _res_icon = "✅ TRUE" if _cmp[c_op] else "❌ FALSE"
                                _sanity_line = (
                                    f"  \n→ {c_left_name}({c_left_period}) on {c_left_series}"
                                    f" = **{_sfmt}** as of {_sd} → currently **{_res_icon}**"
                                )
                except Exception:
                    pass

            elif _is_ind_vs_ind:
                try:
                    from databank.normalizer import DataNormalizer as _DN3
                    from backtest.strategy.indicators import compute_indicator as _ci
                    _sdf_l = _DN3().load_parquet(c_left_series,  Path("DATASETS"))
                    _sdf_r = _DN3().load_parquet(c_right_series, Path("DATASETS"))
                    if (_sdf_l is not None and not _sdf_l.empty
                            and _sdf_r is not None and not _sdf_r.empty):
                        _extra_l = 2 if c_left_name  in ("EMA", "BOLLINGER_UPPER", "BOLLINGER_MID",
                                                          "BOLLINGER_LOWER", "VWAP") else 1
                        _extra_r = 2 if c_right_name in ("EMA", "BOLLINGER_UPPER", "BOLLINGER_MID",
                                                          "BOLLINGER_LOWER", "VWAP") else 1
                        _last_l = _sdf_l.tail(c_left_period  + _extra_l)
                        _last_r = _sdf_r.tail(c_right_period + _extra_r)
                        if (len(_last_l) >= c_left_period  + _extra_l
                                and len(_last_r) >= c_right_period + _extra_r):
                            _sv_l = _ci(c_left_name,  _last_l, c_left_period)
                            _sv_r = _ci(c_right_name, _last_r, c_right_period)
                            _sd_l = _last_l.index[-1].strftime("%Y-%m-%d")
                            _sd_r = _last_r.index[-1].strftime("%Y-%m-%d")
                            _cmp = {
                                ">":  _sv_l >  _sv_r,
                                ">=": _sv_l >= _sv_r,
                                "<":  _sv_l <  _sv_r,
                                "<=": _sv_l <= _sv_r,
                            }
                            if c_op in _cmp:
                                _res_icon = "✅ TRUE" if _cmp[c_op] else "❌ FALSE"
                                _sanity_line = (
                                    f"  \n→ {c_left_name}({c_left_period}) on {c_left_series}"
                                    f" = **{_ind_fmt(c_left_name, _sv_l)}** ({_sd_l})"
                                    f"  vs  {c_right_name}({c_right_period}) on {c_right_series}"
                                    f" = **{_ind_fmt(c_right_name, _sv_r)}** ({_sd_r})"
                                    f" → currently **{_res_icon}**"
                                )
                except Exception:
                    pass

            st.info(f"📋 Condition preview: **{human}**{_sanity_line}")
            _tc1, _tc2 = st.columns(2)
            with _tc1:
                c_persistence = st.number_input(
                    "Consecutive bars required",
                    min_value=0, value=0, step=1,
                    key=f"{key_prefix}_persist",
                    help=(
                        "**0** — fires on the first bar the condition is true.\n\n"
                        "**N > 0** — condition must be true for N consecutive bars before firing.\n\n"
                        "*Not available for crossing operators (they fire on the crossing bar only).*"
                    ),
                    disabled=_is_crossing,
                )
            with _tc2:
                c_lookback = st.number_input(
                    "Latch duration (bars)",
                    min_value=0, value=0, step=1,
                    key=f"{key_prefix}_latch",
                    help=(
                        "**0** — signal is active only while condition remains true.\n\n"
                        "**N > 0** — once triggered, signal stays active for N bars "
                        "even if the condition turns false (useful for crossover signals)."
                    ),
                )
            c_lookback    = int(c_lookback)
            c_persistence = 0 if _is_crossing else int(c_persistence)

            if st.button("✔ Confirm condition", key=f"{key_prefix}_add", type="primary"):
                human_lb = human
                if c_persistence > 0:
                    human_lb += f"  [≥{c_persistence} consecutive bars]"
                if c_lookback > 0:
                    human_lb += f"  [latch {c_lookback} bars]"
                conds.append({
                    "logic":        logic,
                    "left_type":    c_left_type,
                    "left_name":    str(c_left_name),
                    "left_period":  int(c_left_period) if c_left_period else 0,
                    "left_series":  str(c_left_series),
                    "op":           c_op,
                    "right_type":   c_right_type,
                    "right_name":   str(c_right_name),
                    "right_period": int(c_right_period) if c_right_period else 0,
                    "right_series": str(c_right_series),
                    "right_value":  float(c_right_value),
                    "lookback":     int(c_lookback),
                    "persistence":  int(c_persistence),
                    "human":        human_lb,
                })
                st.rerun()

    # ---- Recall an existing strategy ----
    with st.expander("📂 Recall an existing strategy", expanded=False):
        import json as _json_rcl
        _recall_strats = [
            p.stem for p in sorted(Path("strategies").glob("*.py"))
            if not p.name.startswith("_")
            and "# __builder__:" in p.read_text(encoding="utf-8", errors="replace")
        ]
        if not _recall_strats:
            st.caption("No strategies with saved builder state yet. Save a strategy first.")
        else:
            _rcl_c1, _rcl_c2 = st.columns([4, 1])
            with _rcl_c1:
                _recall_sel = st.selectbox(
                    "Strategy", _recall_strats, key="recall_sel",
                    label_visibility="collapsed",
                )
            with _rcl_c2:
                _recall_btn = st.button("⬆️ Load", key="recall_load_btn", use_container_width=True)
            if _recall_btn:
                _rp = Path("strategies") / f"{_recall_sel}.py"
                _loaded = False
                for _rline in _rp.read_text(encoding="utf-8", errors="replace").splitlines():
                    if _rline.startswith("# __builder__: "):
                        _rstate = _json_rcl.loads(_rline[len("# __builder__: "):])
                        _loaded_exec = _rstate.get("exec_mode", "netting")
                        st.session_state.strategy_exec_mode = _loaded_exec
                        # Also sync the selectbox widget key so it reflects the loaded mode
                        _exec_label_map = {
                            "netting":       "Netting — same-bar reversal",
                            "netting_delay": "Netting — next-bar reversal",
                            "hedge":         "Hedge — LONG & SHORT coexist",
                        }
                        st.session_state["strategy_exec_mode_sel"] = _exec_label_map.get(
                            _loaded_exec, "Netting — same-bar reversal"
                        )
                        st.session_state["strat_name_input"] = _rstate.get("name", "")
                        st.session_state["strat_desc_input"] = _rstate.get("desc", "")
                        _rbaskets = _rstate.get("baskets", [])
                        st.session_state.baskets = [
                            {
                                "id": _rb["id"],
                                "assets": _rb.get("assets", []),
                                "weights": _rb.get("weights", {}),
                                "basket_size": _rb.get("basket_size", 10.0),
                                "basket_sl": _rb.get("basket_sl", 2.0),
                                "basket_tp": _rb.get("basket_tp", 5.0),
                                "use_custom_size": _rb.get("use_custom_size", False),
                                "use_sl": _rb.get("use_sl", False),
                                "use_tp": _rb.get("use_tp", False),
                                "entry_conds": _rb.get("entry_conds", []),
                                "exit_conds": _rb.get("exit_conds", []),
                                "short_entry_conds": _rb.get("short_entry_conds", []),
                                "cover_exit_conds": _rb.get("cover_exit_conds", []),
                            }
                            for _rb in _rbaskets
                        ]
                        for _rb in _rbaskets:
                            _bid = _rb["id"]
                            st.session_state[f"{_bid}_entry_conds"]       = _rb.get("entry_conds", [])
                            st.session_state[f"{_bid}_exit_conds"]        = _rb.get("exit_conds", [])
                            st.session_state[f"{_bid}_short_entry_conds"] = _rb.get("short_entry_conds", [])
                            st.session_state[f"{_bid}_cover_exit_conds"]  = _rb.get("cover_exit_conds", [])
                        # Clear stale widget keys so widgets re-initialize from
                        # the freshly loaded basket dicts (pre-init pattern).
                        for _idx in range(len(_rbaskets)):
                            for _stale in list(st.session_state.keys()):
                                if _stale.startswith(f"b{_idx}_"):
                                    del st.session_state[_stale]
                        _loaded = True
                        break
                if _loaded:
                    st.rerun()
                else:
                    st.error("No builder state found in this file.")

    # ---- General info ----
    st.subheader("1. General information")
    col1, col2 = st.columns(2)
    with col1:
        strat_name = st.text_input("Strategy name (e.g. my_rsi_strategy)", key="strat_name_input")
        strat_desc = st.text_input("Short description (optional)", key="strat_desc_input")
    with col2:
        _exec_mode_opts = {
            "Netting — same-bar reversal":   "netting",
            "Netting — next-bar reversal":   "netting_delay",
            "Hedge — LONG & SHORT coexist":  "hedge",
        }
        _exec_mode_keys = list(_exec_mode_opts.keys())
        _exec_cur = st.session_state.strategy_exec_mode
        if "strategy_exec_mode_sel" not in st.session_state:
            _exec_idx = next(
                (i for i, v in enumerate(_exec_mode_opts.values()) if v == _exec_cur), 0
            )
            st.session_state["strategy_exec_mode_sel"] = _exec_mode_keys[_exec_idx]
        _exec_label = st.selectbox(
            "Execution mode",
            _exec_mode_keys,
            key="strategy_exec_mode_sel",
            help=(
                "**Netting — same-bar:** One position per asset at a time. "
                "If a LONG is open and a SHORT signal fires on the same bar, "
                "the LONG is closed and a SHORT is opened immediately.\n\n"
                "*Example: trend-following strategy that reverses direction.*\n\n"
                "**Netting — next-bar:** Same as above, but the new position opens "
                "on the bar following the reversal signal (1-bar delay).\n\n"
                "*Example: end-of-day signals acted on at next open.*\n\n"
                "**Hedge:** LONG and SHORT positions can coexist on the same asset. "
                "Each basket is independent — basket 1 can be LONG while basket 2 "
                "is SHORT on the same symbol.\n\n"
                "*Example: pairs trading, or delta-neutral strategies.*"
            ),
        )
        st.session_state.strategy_exec_mode = _exec_mode_opts[_exec_label]
        _exec_mode_val = st.session_state.strategy_exec_mode

    # ---- Baskets ----
    st.subheader("2. Baskets")
    st.caption(
        "Each basket is a group of assets sharing the same entry/exit conditions "
        "and a basket-level SL/TP. Weights within a basket define each asset's share "
        "of the basket allocation."
    )

    baskets_state = st.session_state.baskets

    # ── Pre-compute automatic basket sizes ("fill remaining space") ──────────
    # Read current use_custom flags and custom sizes from session_state
    _use_custom_flags = [
        st.session_state.get(f"b{_ki}_use_size", _bb.get("use_custom_size", True))
        for _ki, _bb in enumerate(baskets_state)
    ]
    _custom_total = sum(
        st.session_state.get(f"b{_ki}_bsize", _bb.get("basket_size", 10.0))
        for _ki, _bb in enumerate(baskets_state)
        if _use_custom_flags[_ki]
    )
    _n_auto = sum(1 for x in _use_custom_flags if not x)
    _auto_size = round(max(0.0, 100.0 - _custom_total) / _n_auto, 1) if _n_auto > 0 else 0.0
    for _ki, _bb in enumerate(baskets_state):
        _bb["use_custom_size"] = _use_custom_flags[_ki]
        if not _use_custom_flags[_ki]:
            _bb["basket_size"] = _auto_size

    for i, b in enumerate(baskets_state):
        bid = b["id"]
        hcol, dcol = st.columns([9, 1])
        with hcol:
            st.subheader(f"Basket {i + 1}")
        with dcol:
            if len(baskets_state) > 1:
                if st.button("🗑", key=f"del_basket_{i}", help="Delete this basket"):
                    baskets_state.pop(i)
                    st.rerun()

        # Assets — pre-init from basket dict to avoid session_state/default conflict
        if f"b{i}_assets" not in st.session_state:
            st.session_state[f"b{i}_assets"] = b["assets"]
        selected_assets = st.multiselect(
            "Assets", tradeable,
            format_func=lambda t: _tr_lbl_map.get(t, t),
            key=f"b{i}_assets",
        )
        b["assets"] = selected_assets

        # Weights (only shown if >1 asset selected)
        if len(selected_assets) > 1:
            st.caption("Enter any relative weights — they are normalized automatically.")
            w_cols = st.columns(len(selected_assets))
            for j, asset in enumerate(selected_assets):
                with w_cols[j]:
                    _wkey = f"b{i}_w_{asset}"
                    if _wkey not in st.session_state:
                        st.session_state[_wkey] = float(
                            b["weights"].get(asset, round(100.0 / len(selected_assets), 1))
                        )
                    new_w = st.number_input(
                        asset, min_value=0.1, max_value=9999.0,
                        step=1.0, format="%.1f", key=_wkey,
                    )
                    b["weights"][asset] = new_w
            # Remove stale weights for assets no longer selected
            b["weights"] = {a: b["weights"][a] for a in selected_assets if a in b["weights"]}

            # ── Live normalized breakdown ────────────────────────────────────
            _raw_total = sum(b["weights"].values())
            # For custom-sized baskets, read from session_state so the breakdown
            # reflects the live widget value. For auto-sized baskets, use
            # b["basket_size"] which was already computed above as _auto_size,
            # bypassing stale session_state from when the widget was still shown.
            if b.get("use_custom_size", True):
                _basket_sz = st.session_state.get(f"b{i}_bsize", b.get("basket_size", 10.0))
            else:
                _basket_sz = b.get("basket_size", 10.0)
            if _raw_total > 0:
                _parts = []
                for asset in selected_assets:
                    _eff_pct  = b["weights"][asset] / _raw_total * 100
                    _cap_pct  = b["weights"][asset] / _raw_total * _basket_sz
                    _parts.append(f"**{asset}** {_eff_pct:.1f}% → {_cap_pct:.2f}% of capital")
                st.caption("Effective allocation:  " + "  ·  ".join(_parts))

        elif len(selected_assets) == 1:
            b["weights"] = {selected_assets[0]: 100.0}
        else:
            b["weights"] = {}

        # Risk params — size, SL, TP
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            if f"b{i}_use_size" not in st.session_state:
                st.session_state[f"b{i}_use_size"] = b.get("use_custom_size", True)
            b["use_custom_size"] = st.checkbox(
                "Custom basket size", key=f"b{i}_use_size",
                help=(
                    "**Checked** — set a custom allocation % for this basket.\n\n"
                    "**Unchecked** — automatic: this basket fills whatever portfolio space "
                    "is left after all custom baskets are sized.\n\n"
                    "*Multiple unchecked baskets share the remaining space equally.*"
                ),
            )
            if b["use_custom_size"]:
                if f"b{i}_bsize" not in st.session_state:
                    st.session_state[f"b{i}_bsize"] = max(0.1, float(b["basket_size"]))
                b["basket_size"] = st.number_input(
                    "Basket size (%)",
                    min_value=0.1, max_value=100.0, step=1.0, format="%.1f",
                    key=f"b{i}_bsize",
                )
            else:
                st.caption(f"Auto — **{b['basket_size']:.1f}%** (fills remaining portfolio space)")
        with rc2:
            if f"b{i}_use_sl" not in st.session_state:
                st.session_state[f"b{i}_use_sl"] = b["use_sl"]
            b["use_sl"] = st.checkbox("Enable Stop Loss", key=f"b{i}_use_sl")
            if b["use_sl"]:
                if f"b{i}_sl" not in st.session_state:
                    st.session_state[f"b{i}_sl"] = float(b["basket_sl"] or 2.0)
                b["basket_sl"] = st.number_input(
                    "Stop Loss (%)", min_value=0.1, max_value=50.0,
                    step=0.5, format="%.1f", key=f"b{i}_sl",
                )
        with rc3:
            if f"b{i}_use_tp" not in st.session_state:
                st.session_state[f"b{i}_use_tp"] = b["use_tp"]
            b["use_tp"] = st.checkbox("Enable Take Profit", key=f"b{i}_use_tp")
            if b["use_tp"]:
                if f"b{i}_tp" not in st.session_state:
                    st.session_state[f"b{i}_tp"] = float(b["basket_tp"] or 5.0)
                b["basket_tp"] = st.number_input(
                    "Take Profit (%)", min_value=0.1, max_value=200.0,
                    step=0.5, format="%.1f", key=f"b{i}_tp",
                )

        # ── Total allocation indicator ───────────────────────────────────────
        _total_alloc  = sum(bb["basket_size"] for bb in baskets_state)
        _auto_mode    = not any(bb.get("use_custom_size", True) for bb in baskets_state)
        _auto_label   = "  *(automatic equal split)*" if _auto_mode else ""
        if _total_alloc > 100.0:
            _lev = _total_alloc / 100.0
            st.info(
                f"⚡ Total allocation: **{_total_alloc:.1f}%** — leverage **{_lev:.2f}×**  "
                f"*(combined baskets exceed 100% of portfolio)*",
                icon=None,
            )
        elif abs(_total_alloc - 100.0) < 0.05:
            st.success(f"✓ Total allocation: **{_total_alloc:.1f}%** — fully invested.{_auto_label}", icon=None)
        else:
            _remaining = 100.0 - _total_alloc
            st.caption(f"Total allocation: **{_total_alloc:.1f}%** — {_remaining:.1f}% unallocated.{_auto_label}")

        # Ensure per-basket cond list keys exist in session_state
        # Use basket ID (not index i) as key — robust against deletions/reordering
        _cond_keys = {
            "entry":       f"{bid}_entry_conds",
            "exit":        f"{bid}_exit_conds",
            "short_entry": f"{bid}_short_entry_conds",
            "cover_exit":  f"{bid}_cover_exit_conds",
        }
        for _ck_name, _ck in _cond_keys.items():
            if _ck not in st.session_state:
                st.session_state[_ck] = []

        # Sync basket dict from session state (cond lists live in session_state)
        b["entry_conds"]       = st.session_state[_cond_keys["entry"]]
        b["exit_conds"]        = st.session_state[_cond_keys["exit"]]
        b["short_entry_conds"] = st.session_state[_cond_keys["short_entry"]]
        b["cover_exit_conds"]  = st.session_state[_cond_keys["cover_exit"]]

        with st.expander(f"Entry conditions (LONG) — basket {i + 1}", expanded=False):
            cond_editor(f"{bid}_entry", _cond_keys["entry"])
        with st.expander(f"Exit conditions (FLAT) — basket {i + 1}", expanded=False):
            st.caption("Stop loss and take profit at basket level are handled automatically.")
            cond_editor(f"{bid}_exit", _cond_keys["exit"])
        with st.expander(f"Short entry conditions — basket {i + 1}", expanded=False):
            st.caption("Optional — leave empty for a long-only basket.")
            cond_editor(f"{bid}_short_entry", _cond_keys["short_entry"])
        with st.expander(f"Cover exit conditions — basket {i + 1}", expanded=False):
            st.caption("Conditions to close a short position.")
            cond_editor(f"{bid}_cover_exit", _cond_keys["cover_exit"])

        st.markdown("---")

    if st.button("➕ Add another basket"):
        new_idx = len(baskets_state) + 1
        baskets_state.append({
            "id":             f"basket_{new_idx}",
            "assets":         [],
            "weights":        {},
            "basket_size":       10.0,
            "basket_sl":         2.0,
            "basket_tp":         5.0,
            "use_custom_size":   False,
            "use_sl":            False,
            "use_tp":            False,
            "entry_conds":       [],
            "exit_conds":        [],
            "short_entry_conds": [],
            "cover_exit_conds":  [],
        })
        st.rerun()

    # ---- Generate ----
    st.subheader("3. Generate strategy")

    # Netting validation: each asset can only appear in one basket
    if st.session_state.strategy_exec_mode in ("netting", "netting_delay"):
        _seen_assets: dict[str, int] = {}
        _netting_conflicts: list[str] = []
        for _bi, _bb in enumerate(baskets_state, 1):
            for _a in _bb.get("assets", []):
                if _a in _seen_assets:
                    _netting_conflicts.append(
                        f"**{_a}** appears in basket {_seen_assets[_a]} and basket {_bi}"
                    )
                else:
                    _seen_assets[_a] = _bi
        if _netting_conflicts:
            st.warning(
                "⚠️ In **Netting** mode, each asset can only be in one basket. "
                "Switch to **Hedge** mode to allow the same asset across multiple baskets.\n\n"
                + "\n\n".join(_netting_conflicts)
            )

    if not strat_name:
        st.warning("Please enter a strategy name.")
    else:
        import re as _re

        def _build_code():
            from strategy_builder import CodeGenerator, Condition, Basket as _Basket

            def _to_conds(lst):
                return [Condition(
                    left_type=c["left_type"], left_name=c["left_name"],
                    left_period=c["left_period"], left_series=c["left_series"],
                    op=c["op"],
                    right_type=c["right_type"], right_name=c["right_name"],
                    right_period=c["right_period"], right_series=c["right_series"],
                    right_value=c["right_value"],
                    logic=c["logic"].split()[0],
                    lookback=c.get("lookback", 0),
                    persistence=c.get("persistence", 0),
                ) for c in lst]

            safe_name  = _re.sub(r"[^a-z0-9_]", "_", strat_name.lower().strip())
            class_name = "".join(w.capitalize() for w in safe_name.split("_"))

            bk_objects = []
            for i, b in enumerate(baskets_state):
                assets = b["assets"]
                if not assets:
                    continue
                # Normalize weights
                raw_w = {a: b["weights"].get(a, 1.0) for a in assets}
                total_w = sum(raw_w.values()) or 1.0
                norm_w = {a: raw_w[a] / total_w for a in assets}
                bk_objects.append(_Basket(
                    id=b["id"],
                    assets=assets,
                    weights=norm_w,
                    basket_size=b["basket_size"] / 100,
                    basket_sl=b["basket_sl"] / 100 if b["use_sl"] else None,
                    basket_tp=b["basket_tp"] / 100 if b["use_tp"] else None,
                    entry=_to_conds(st.session_state.get(f"{b['id']}_entry_conds", [])),
                    exit_=_to_conds(st.session_state.get(f"{b['id']}_exit_conds", [])),
                    short_entry=_to_conds(st.session_state.get(f"{b['id']}_short_entry_conds", [])),
                    cover_exit=_to_conds(st.session_state.get(f"{b['id']}_cover_exit_conds", [])),
                ))

            if not bk_objects:
                return None, safe_name

            code = CodeGenerator().generate_multi(
                name=safe_name, class_name=class_name,
                baskets=bk_objects,
                description=strat_desc or safe_name,
                execution_mode=st.session_state.strategy_exec_mode,
            )

            # Embed full builder state as a JSON comment after the module docstring
            import json as _json_bs
            _bs_state = {
                "name": safe_name,
                "desc": strat_desc or safe_name,
                "exec_mode": st.session_state.strategy_exec_mode,
                "baskets": [
                    {
                        "id": b["id"],
                        "assets": b["assets"],
                        "weights": b["weights"],
                        "basket_size": b["basket_size"],
                        "basket_sl": b["basket_sl"],
                        "basket_tp": b["basket_tp"],
                        "use_custom_size": b.get("use_custom_size", False),
                        "use_sl": b.get("use_sl", False),
                        "use_tp": b.get("use_tp", False),
                        "entry_conds": st.session_state.get(f"{b['id']}_entry_conds", []),
                        "exit_conds": st.session_state.get(f"{b['id']}_exit_conds", []),
                        "short_entry_conds": st.session_state.get(f"{b['id']}_short_entry_conds", []),
                        "cover_exit_conds": st.session_state.get(f"{b['id']}_cover_exit_conds", []),
                    }
                    for b in baskets_state if b["assets"]
                ],
            }
            _state_line = f"# __builder__: {_json_bs.dumps(_bs_state, ensure_ascii=False)}"
            _lines = code.split("\n")
            for _idx, _ln in enumerate(_lines):
                if _idx > 0 and _ln.strip() == '"""':
                    _lines.insert(_idx + 1, _state_line)
                    break
            code = "\n".join(_lines)

            return code, safe_name

        col_p, col_s = st.columns(2)
        with col_p:
            if st.button("👁  Preview code", use_container_width=True):
                code, _ = _build_code()
                if code:
                    st.code(code, language="python")
                else:
                    st.warning("Add at least one basket with assets and entry conditions.")
        with col_s:
            if st.button("💾  Save strategy", type="primary", use_container_width=True):
                code, safe_name = _build_code()
                if not code:
                    st.warning("Add at least one basket with assets and entry conditions.")
                elif (Path("strategies") / f"{safe_name}.py").exists():
                    st.session_state["_save_overwrite_pending"] = (safe_name, code)
                else:
                    (Path("strategies") / f"{safe_name}.py").write_text(code, encoding="utf-8")
                    _list_strategies.clear()
                    st.session_state["_just_saved"] = safe_name

        # ── Overwrite confirmation ────────────────────────────────────────
        if st.session_state.get("_save_overwrite_pending"):
            _ow_name, _ow_code = st.session_state["_save_overwrite_pending"]
            st.warning(f"`{_ow_name}.py` already exists. Overwrite it?")
            _ow1, _ow2 = st.columns([1, 1])
            with _ow1:
                if st.button("Yes, overwrite", key="save_ow_confirm", type="primary"):
                    (Path("strategies") / f"{_ow_name}.py").write_text(_ow_code, encoding="utf-8")
                    _list_strategies.clear()
                    st.session_state.pop("_save_overwrite_pending", None)
                    st.session_state["_just_saved"] = _ow_name
            with _ow2:
                if st.button("Cancel", key="save_ow_cancel"):
                    st.session_state.pop("_save_overwrite_pending", None)
                    st.rerun()

        # ── Post-save reset ───────────────────────────────────────────────
        if st.session_state.get("_just_saved"):
            _saved_name = st.session_state.pop("_just_saved")
            st.success(f"Strategy saved: `strategies/{_saved_name}.py`")
            st.caption("It will appear in the Run Backtest page.")
            st.session_state.entry_conds       = []
            st.session_state.exit_conds        = []
            st.session_state.short_entry_conds = []
            st.session_state.cover_exit_conds  = []
            st.session_state.baskets = [
                {
                    "id": "basket_1", "assets": [], "weights": {},
                    "basket_size": 10.0, "basket_sl": 2.0, "basket_tp": 5.0,
                    "use_custom_size": False, "use_sl": False, "use_tp": False,
                    "entry_conds": [], "exit_conds": [],
                    "short_entry_conds": [], "cover_exit_conds": [],
                }
            ]
            st.session_state.strategy_exec_mode = "netting"
            st.session_state["_builder_reset_pending"] = True
            for key in list(st.session_state.keys()):
                if key.startswith("basket_") and "_conds" in key:
                    del st.session_state[key]
            st.rerun()


# ===========================================================================
# PAGE: REVIEW STRATEGY
# ===========================================================================

elif page == "🔍 Review Strategy":
    st.title("🔍 Review Strategy")

    strategies = _list_strategies()
    if not strategies:
        st.error("No strategies found in `strategies/`.")
        st.stop()

    # ── Selector + delete ──────────────────────────────────────────────────
    sel_col, del_col = st.columns([4, 1])
    with sel_col:
        selected_strat = st.selectbox("Select a strategy", strategies, key="review_sel")
    with del_col:
        st.write("")
        st.write("")
        if st.button("🗑 Delete", key="review_del", type="secondary"):
            st.session_state["_strat_del_pending"] = selected_strat

    if st.session_state.get("_strat_del_pending") == selected_strat:
        st.warning(f"Delete **{selected_strat}** ? This cannot be undone.")
        _dc1, _dc2 = st.columns([1, 1])
        with _dc1:
            if st.button("Yes, delete", key="strat_del_confirm", type="primary"):
                p = Path("strategies") / f"{selected_strat}.py"
                if p.exists():
                    p.unlink()
                _list_strategies.clear()
                st.session_state.pop("_strat_del_pending", None)
                st.session_state.pop("review_sel", None)
                st.session_state.pop(f"review_code_{selected_strat}", None)
                st.rerun()
        with _dc2:
            if st.button("Cancel", key="strat_del_cancel"):
                st.session_state.pop("_strat_del_pending", None)
                st.rerun()

    strat_path = Path("strategies") / f"{selected_strat}.py"

    # ── Load source into editor state ─────────────────────────────────────
    # Use a key tied to the selected strategy so the editor resets on change.
    editor_key = f"review_code_{selected_strat}"
    if editor_key not in st.session_state:
        st.session_state[editor_key] = strat_path.read_text(encoding="utf-8", errors="replace")

    tab_overview, tab_modify = st.tabs(["📋 Overview", "✏️ Modify"])

    # ── Overview ──────────────────────────────────────────────────────────
    with tab_overview:
        import re as _re
        import ast as _ast

        src_text = strat_path.read_text(encoding="utf-8", errors="replace")
        _D = "\u2500"   # ─  U+2500  (section header dashes)
        _E = "\u2550"   # ═  U+2550  (basket separator)

        # ── 1. Metadata ───────────────────────────────────────────────────
        def _parse_meta(src: str) -> dict:
            m = _re.search(r"Strategie\s*:\s*(.+)", src)
            desc = m.group(1).strip() if m else ""
            m = _re.search(r"Generee le\s+(.+)", src)
            gen  = m.group(1).strip() if m else ""
            m = _re.search(r'execution_mode\s*=\s*["\'](\w+)["\']', src)
            mode = m.group(1).strip() if m else "netting"
            nb   = len(_re.findall(r"_B\d+_ASSETS\s*=", src))
            return {"description": desc, "generated": gen,
                    "execution_mode": mode, "n_baskets": nb}

        # ── 2. Basket class-level attributes ─────────────────────────────
        def _parse_basket_attrs(src: str, i: int) -> dict:
            def _safe_eval(pat, src, default):
                m = _re.search(pat, src)
                if not m:
                    return default
                try:
                    return _ast.literal_eval(m.group(1).strip())
                except Exception:
                    return default
            assets = list(_safe_eval(rf"_B{i}_ASSETS\s*=\s*(\(.*?\))", src, ()))
            sizes  = _safe_eval(rf"_B{i}_SIZES\s*=\s*(\{{[^}}]*\}})", src, {})
            sl_raw = _safe_eval(rf"_B{i}_SL\s*=\s*([^\n]+)", src, None)
            tp_raw = _safe_eval(rf"_B{i}_TP\s*=\s*([^\n]+)", src, None)
            sl = float(sl_raw) if sl_raw is not None else None
            tp = float(tp_raw) if tp_raw is not None else None
            return {"assets": assets, "sizes": sizes, "sl": sl, "tp": tp}

        # ── 3. Extract the if/elif block for basket i in on_bar ──────────
        def _extract_basket_block(src: str, i: int) -> str:
            m = _re.search(r"def on_bar\(self[^)]*\)[^:]*:\n(.*)", src, _re.DOTALL)
            if not m:
                return ""
            body = m.group(1)
            sm   = _re.search(rf"\s*if\s+symbol\s+in\s+self\._B{i}_ASSETS\s*:", body)
            if not sm:
                return ""
            block = body[sm.end():]
            # Cut at the next basket separator (═══) or next basket block
            cut = _re.search(
                rf"(?:#\s*{_E}{{3,}}|\s*(?:if|elif)\s+symbol\s+in\s+self\._B\d+_ASSETS\s*:)",
                block,
            )
            return block[:cut.start()] if cut else block

        # ── 4. Extract ─── subsections, excluding Signals ────────────────
        def _extract_subsections(block: str) -> dict:
            header_re = _re.compile(
                rf"\s*#\s*{_D}+\s*([^{_D}\n]+?)\s*{_D}+[^\n]*\n"
            )
            matches = list(header_re.finditer(block))
            result  = {}
            for idx, hm in enumerate(matches):
                name = hm.group(1).strip()
                if name.lower() == "signals":
                    break
                start = hm.end()
                end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(block)
                result[name] = block[start:end]
            return result

        def _get_sub(subs: dict, name: str) -> str:
            for k, v in subs.items():
                if k.strip().lower() == name.lower():
                    return v
            return ""

        # ── 5. Variable / expression decoder ─────────────────────────────
        def _decode_var(v: str) -> str:
            v = v.strip().strip("()")
            # series_indicator: _sma_10_spx, _ema_20_spx, _sma_25_pctabovevwap_ny
            m = _re.match(r"_([a-z]+)_(\d+)_([a-z][a-z0-9_]*)$", v)
            if m:
                series = m.group(3).upper().replace("_", ".")
                return f"{m.group(1).upper()}({m.group(2)}) on {series}"
            # main indicator: _rsi_14, _sma_20, _bollinger_lower_20, _atr_14
            m = _re.match(r"_([a-z][a-z0-9_]*)_(\d+)$", v)
            if m:
                return f"{m.group(1).upper().replace('_', '_')}({m.group(2)})"
            # raw series (bare lowercase var like ndx, spx)
            if _re.match(r"^[a-z][a-z0-9_]*$", v):
                return v.upper().replace("_", ".")
            # bar field: bar["close"]
            mb = _re.match(r'bar\["(\w+)"\]', v)
            if mb:
                return mb.group(1)
            return v

        def _decode_expr(expr: str) -> str:
            expr = expr.strip().strip("()")
            # Crossing: LEFT >= RIGHT and LEFT_prev < RIGHT[_prev?]
            # Works for both variable right side (B_prev) and value right side (same V)
            m = _re.search(
                r"(\w+)\s*(>=|<=)\s*(\S+)\s+and\s+\1_prev\s*(?:<=|<|>=|>)\s*\S+",
                expr,
            )
            if m:
                left_v  = m.group(1)
                op      = m.group(2)
                right_v = m.group(3).rstrip(")")
                direction = "crosses above" if op == ">=" else "crosses below"
                return f"{_decode_var(left_v)}  {direction}  {_decode_var(right_v)}"
            # Simple comparison — split on first operator only
            for op in (">=", "<=", ">", "<"):
                if op in expr:
                    left, right = expr.split(op, 1)
                    # Skip if right side contains 'and' (would be a mismatched crossing)
                    right = right.strip()
                    if " and " not in right:
                        return f"{_decode_var(left.strip())}  {op}  {_decode_var(right)}"
            return expr

        # ── 6. Parse conditions from a subsection block ───────────────────
        def _parse_conditions(block: str) -> list[dict]:
            """
            Returns list of {"text": str, "connector": "IF"|"AND"|"OR"}.

            Two code paths:
            - State path (has _raw_N = ...): human-readable comments above each
              _raw_N line are used directly as condition text. Logic (AND/OR) comes
              from the final _var = (...) combination block.
            - Fast path (no _raw_N): decode expressions from the _var = (...) block.
            """
            if not block.strip():
                return []

            lines = block.splitlines()
            has_state = any(_re.match(r"\s*_raw_\d+\s*=", l) for l in lines)

            if has_state:
                # Collect the # comment lines that precede each _raw_N = line.
                # The generator emits them as: `# human_readable()` text
                # Skip structural comment markers (─, ═, "Snapshot", etc.)
                comments = []
                prev_was_raw = False
                for ln in lines:
                    ls = ln.strip()
                    is_raw = bool(_re.match(r"_raw_\d+\s*=", ls))
                    if is_raw:
                        prev_was_raw = True
                        continue
                    if ls.startswith("#"):
                        text = ls.lstrip("#").strip()
                        if (text
                                and not _re.search(rf"[{_D}{_E}]", text)
                                and not text.lower().startswith(("snapshot", "asset ind"))):
                            comments.append(text)
                    prev_was_raw = False

                # Extract AND / OR connectors from the final _var = (\n  (_eff_N)\n  and/or ...\n)
                final_m = _re.search(
                    r"_\w+\s*=\s*\(\n(.*?)\n\s*\)", block, _re.DOTALL
                )
                connectors: list[str] = []
                if final_m:
                    for ln in final_m.group(1).splitlines():
                        ls = ln.strip().lower()
                        if ls.startswith("and ") or ls == "and":
                            connectors.append("AND")
                        elif ls.startswith("or ") or ls == "or":
                            connectors.append("OR")

                result = []
                for idx, text in enumerate(comments):
                    # Normalize French [sur X] → on X
                    text = _re.sub(r"\[sur\s+([^\]]+)\]", r"on \1", text)
                    conn = "IF" if idx == 0 else (
                        connectors[idx - 1] if idx - 1 < len(connectors) else "AND"
                    )
                    result.append({"text": text, "connector": conn})
                return result

            else:
                # Fast path: decode the _var = (\n  (expr)\n  and/or (expr)\n) block
                final_m = _re.search(
                    r"_(?:entry|exit|short_entry|cover)\s*=\s*\(\n(.*?)\n\s*\)",
                    block, _re.DOTALL,
                )
                if not final_m:
                    return []

                result    = []
                connector = "IF"
                for ln in final_m.group(1).splitlines():
                    ls = ln.strip()
                    if not ls:
                        continue
                    if ls.lower().startswith("and "):
                        connector = "AND"
                        ls = ls[4:]
                    elif ls.lower().startswith("or "):
                        connector = "OR"
                        ls = ls[3:]
                    ls = ls.strip().strip("()")
                    if not ls or _re.match(r"_eff_\d+$", ls):
                        continue
                    result.append({"text": _decode_expr(ls), "connector": connector})
                    connector = "AND"
                return result

        # ── 7. Render a condition list cleanly ───────────────────────────
        def _render_conds(conds: list[dict]) -> None:
            for c in conds:
                conn = c["connector"]
                text = c["text"]
                # Style timing suffixes distinctly
                text = _re.sub(
                    r"(\[latch \d+ bars?\]|\[for \d+ consecutive bars?\])",
                    r"*`\1`*",
                    text,
                )
                if conn == "IF":
                    st.markdown(f"**IF** &nbsp;&nbsp; {text}")
                else:
                    st.markdown(f"*{conn}* &nbsp; {text}")

        # ── Display ───────────────────────────────────────────────────────
        meta      = _parse_meta(src_text)
        exec_mode = meta["execution_mode"]
        n_baskets = meta["n_baskets"]

        exec_labels = {
            "netting":       "🟡 Netting — same-bar reversal",
            "netting_delay": "🟡 Netting — next-bar reversal",
            "hedge":         "🔵 Hedge — LONG & SHORT coexist",
        }
        exec_label = exec_labels.get(exec_mode, f"🟡 {exec_mode}")

        # Header row
        h1, h2, h3 = st.columns([3, 2, 2])
        h1.markdown(f"### {meta['description'] or selected_strat}")
        h2.markdown(f"🕒 *{meta['generated']}*")
        h3.markdown(f"**{exec_label}**")
        st.caption(f"📁 `strategies/{selected_strat}.py`")
        st.divider()

        if n_baskets == 0:
            st.info("Non-generated strategy — use the Modify tab to view the source.")
        else:
            for bi in range(1, n_baskets + 1):
                attrs    = _parse_basket_attrs(src_text, bi)
                assets   = attrs["assets"]
                sizes    = attrs["sizes"]
                sl       = attrs["sl"]
                tp       = attrs["tp"]
                total_sz = sum(sizes.values()) if sizes else 0.0

                with st.container(border=True):
                    # ── Basket header ────────────────────────────────────
                    hc1, hc2, hc3, hc4 = st.columns([4, 1, 1, 1])
                    hc1.markdown(f"#### Basket {bi} — {', '.join(assets)}")
                    hc2.metric("Size",        f"{total_sz * 100:.0f}%")
                    hc3.metric("Stop loss",   f"{sl * 100:.1f}%"  if sl else "—")
                    hc4.metric("Take profit", f"{tp * 100:.1f}%"  if tp else "—")

                    if len(assets) > 1 and sizes:
                        weights_str = "  ·  ".join(
                            f"**{a}** {sizes.get(a, 0) / total_sz * 100:.0f}%"
                            for a in assets
                        )
                        st.caption(f"Allocation: {weights_str}")

                    st.divider()

                    # ── Parse conditions ──────────────────────────────────
                    block = _extract_basket_block(src_text, bi)
                    subs  = _extract_subsections(block)

                    entry_conds = _parse_conditions(_get_sub(subs, "Entry"))
                    short_conds = _parse_conditions(_get_sub(subs, "Short entry"))
                    exit_conds  = _parse_conditions(_get_sub(subs, "Exit"))
                    cover_conds = _parse_conditions(_get_sub(subs, "Cover exit"))

                    has_short = bool(short_conds or cover_conds)
                    has_long  = bool(entry_conds or exit_conds)

                    sl_tp_note = (
                        "SL/TP only"  if (sl or tp) else "—"
                    )

                    if has_short and has_long:
                        col_en, col_ex, col_sh, col_cv = st.columns(4)
                        cols = {
                            "entry": col_en, "exit": col_ex,
                            "short": col_sh, "cover": col_cv,
                        }
                    elif has_short:
                        col_sh, col_cv = st.columns(2)
                        cols = {"short": col_sh, "cover": col_cv}
                    else:
                        col_en, col_ex = st.columns(2)
                        cols = {"entry": col_en, "exit": col_ex}

                    if "entry" in cols:
                        with cols["entry"]:
                            st.markdown("🟢 **Entry — LONG**")
                            if entry_conds:
                                _render_conds(entry_conds)
                            else:
                                st.caption("—")

                    if "exit" in cols:
                        with cols["exit"]:
                            st.markdown("⬜ **Exit — FLAT**")
                            if exit_conds:
                                _render_conds(exit_conds)
                            else:
                                st.caption(sl_tp_note)

                    if "short" in cols:
                        with cols["short"]:
                            st.markdown("🔴 **Entry — SHORT**")
                            if short_conds:
                                _render_conds(short_conds)
                            else:
                                st.caption("—")

                    if "cover" in cols:
                        with cols["cover"]:
                            st.markdown("⬜ **Exit — COVER**")
                            if cover_conds:
                                _render_conds(cover_conds)
                            else:
                                st.caption(sl_tp_note)

    # ── Modify ────────────────────────────────────────────────────────────
    with tab_modify:
        st.subheader("Source code")
        edited_code = st.text_area(
            label="Edit the strategy code below",
            value=st.session_state[editor_key],
            height=520,
            key=f"review_editor_{selected_strat}",
            label_visibility="collapsed",
        )

        save_col, reload_col, _ = st.columns([1, 1, 4])
        with save_col:
            if st.button("💾  Save changes", type="primary", use_container_width=True):
                strat_path.write_text(edited_code, encoding="utf-8")
                _list_strategies.clear()
                st.session_state[editor_key] = edited_code
                mod_key = f"strategies.{selected_strat}"
                if mod_key in sys.modules:
                    del sys.modules[mod_key]
                st.success("Strategy saved.")
        with reload_col:
            if st.button("↺  Reload from disk", use_container_width=True):
                st.session_state[editor_key] = strat_path.read_text(
                    encoding="utf-8", errors="replace"
                )
                st.rerun()


# ===========================================================================
# PAGE: DATA BANK
# ===========================================================================

elif page == "🗄️ Data Bank":
    st.title("🗄️ Data Bank")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        ["📋 Datasets", "📥 Import CSV", "📥 Import TradingView",
         "📈 Yahoo Finance", "📊 FRED", "🔗 Derived series"]
    )

    with tab1:
        # ── Provider badges ──────────────────────────────────────────────────
        _PROVIDER_BADGE = {
            "tradingview": "📊 TradingView",
            "yfinance":    "📈 Yahoo Finance",
            "fred":        "🏛️ FRED",
            "alfred":      "🏛️ FRED/ALFRED",
            "csv":         "📁 CSV",
            "derived":     "🔗 Derived",
        }
        _CLASS_BADGE = {
            "index":     "📉 Index",
            "equity":    "🏢 Equity",
            "fx":        "💱 FX",
            "crypto":    "🪙 Crypto",
            "indicator": "🔬 Indicator",
            "other":     "❓ Other",
        }

        try:
            import pandas as pd
            from databank.catalog import list_assets
            assets = list_assets()
            if assets:
                # ── Build display table ──────────────────────────────────────
                rows = []
                for a in assets:
                    prov = a.get("provider", "")
                    cls  = a.get("class", "")
                    rows.append({
                        "Ticker":    a.get("ticker", ""),
                        "Name":      a.get("name", ""),
                        "Source":    _PROVIDER_BADGE.get(prov, prov),
                        "Class":     _CLASS_BADGE.get(cls, cls),
                        "Unit":      a.get("currency", ""),
                        "Bars":      f"{a.get('n_bars', 0):,}",
                        "Start":     a.get("start", ""),
                        "End":       a.get("end", ""),
                    })
                display_df = pd.DataFrame(rows)

                # ── Summary counts ───────────────────────────────────────────
                n_total = len(assets)
                by_provider = {}
                for a in assets:
                    p = _PROVIDER_BADGE.get(a.get("provider",""), a.get("provider",""))
                    by_provider[p] = by_provider.get(p, 0) + 1

                summary_parts = [f"**{n_total} series**"] + [
                    f"{badge}: {n}" for badge, n in sorted(by_provider.items())
                ]
                st.caption("  ·  ".join(summary_parts))

                st.dataframe(display_df, use_container_width=True, hide_index=True,
                             column_config={
                                 "Ticker": st.column_config.TextColumn(width="small"),
                                 "Name":   st.column_config.TextColumn(width="medium"),
                                 "Source": st.column_config.TextColumn(width="medium"),
                                 "Class":  st.column_config.TextColumn(width="small"),
                                 "Unit":   st.column_config.TextColumn(width="small"),
                                 "Bars":   st.column_config.TextColumn(width="small"),
                                 "Start":  st.column_config.TextColumn(width="small"),
                                 "End":    st.column_config.TextColumn(width="small"),
                             })

                # ── Note about intentional "duplicates" ──────────────────────
                _dup_note = []
                tickers_present = {a["ticker"] for a in assets}
                if "VIX" in tickers_present and "VIXYAHOO" in tickers_present:
                    _dup_note.append(
                        "**VIX** (TradingView, from 2007) and **VIXYAHOO** "
                        "(Yahoo Finance, from 1990) are intentionally separate — "
                        "same underlying, different sources and history lengths."
                    )
                if _dup_note:
                    with st.expander("ℹ️  Notes on similar series", expanded=False):
                        for note in _dup_note:
                            st.markdown(f"- {note}")

                # ── Quick preview ────────────────────────────────────────────
                st.divider()
                st.subheader("Quick preview")
                _pv_do_labels, _pv_do_tickers = _build_data_options()
                _pv_lbl_map = dict(zip(_pv_do_tickers, _pv_do_labels))
                _prev_ticker = st.selectbox(
                    "Select a series",
                    _pv_do_tickers or [a["ticker"] for a in assets],
                    format_func=lambda t: _pv_lbl_map.get(t, t),
                    key="preview_ticker",
                )
                if _prev_ticker:
                    try:
                        from databank.normalizer import DataNormalizer
                        import plotly.graph_objects as go

                        _PV_ORANGE      = "#F57C00"
                        _PV_ORANGE_PALE = "rgba(245,124,0,0.12)"

                        _pv_df = DataNormalizer().load_parquet(_prev_ticker, Path("DATASETS"))
                        if _pv_df is not None and not _pv_df.empty:

                            # ── KPI row ──────────────────────────────────────
                            _pv_c1, _pv_c2, _pv_c3, _pv_c4 = st.columns(4)
                            _pv_c1.metric("Bars",       f"{len(_pv_df):,}")
                            _pv_c2.metric("Start",      str(_pv_df.index[0].date()))
                            _pv_c3.metric("End",        str(_pv_df.index[-1].date()))
                            _pv_c4.metric("Last close", f"{_pv_df['close'].iloc[-1]:,.4g}")

                            # ── Range selector — server-side filtering ────────
                            # Filtering before passing to Plotly is the only way
                            # to guarantee the Y axis scales to the visible window.
                            _PV_RANGE_DAYS = {
                                "6M": 180, "1Y": 365, "3Y": 1095,
                                "5Y": 1825, "10Y": 3650, "All": None,
                            }
                            # Rangeslider grab-handle colour (Plotly SVG only — no side-effects)
                            st.markdown(
                                "<style>"
                                ".rangeslider-grabber-min > .rangeslider-grabarea,"
                                ".rangeslider-grabber-max > .rangeslider-grabarea"
                                "{ fill: " + _PV_ORANGE + " !important; }"
                                ".rangeslider-grabber-min > path,"
                                ".rangeslider-grabber-max > path"
                                "{ stroke: " + _PV_ORANGE + " !important; }"
                                "</style>",
                                unsafe_allow_html=True,
                            )

                            # Range selector + "rescale Y" button on the same row
                            _pv_rc1, _pv_rc2 = st.columns([1, 8])
                            with _pv_rc1:
                                _pv_rescale = st.button(
                                    "↺ Scale",
                                    key="pv_rescale_y",
                                    help="Reset Y axis to fit the selected time range",
                                    use_container_width=True,
                                )
                            if _pv_rescale:
                                st.session_state["pv_rescale_n"] = (
                                    st.session_state.get("pv_rescale_n", 0) + 1
                                )
                            with _pv_rc2:
                                try:
                                    _pv_range_sel = st.segmented_control(
                                        "Range",
                                        list(_PV_RANGE_DAYS.keys()),
                                        default="1Y",
                                        key="preview_range",
                                        label_visibility="collapsed",
                                    ) or "1Y"
                                except AttributeError:
                                    _pv_range_sel = st.radio(
                                        "Range",
                                        list(_PV_RANGE_DAYS.keys()),
                                        index=1,
                                        horizontal=True,
                                        key="preview_range",
                                        label_visibility="collapsed",
                                    )

                            # ── Window bounds from range selection ───────────
                            _pv_end_dt    = _pv_df.index[-1]
                            _pv_days      = _PV_RANGE_DAYS[_pv_range_sel]
                            _pv_win_start = (
                                _pv_end_dt - pd.Timedelta(days=_pv_days)
                                if _pv_days else _pv_df.index[0]
                            )
                            _pv_plot = _pv_df[_pv_df.index >= _pv_win_start]

                            # Y range — window + 6 % padding
                            _pv_y_lo  = float(_pv_plot["close"].min())
                            _pv_y_hi  = float(_pv_plot["close"].max())
                            _pv_y_pad = (_pv_y_hi - _pv_y_lo) * 0.06
                            _pv_y_range = [
                                round(_pv_y_lo - _pv_y_pad, 6),
                                round(_pv_y_hi + _pv_y_pad, 6),
                            ]

                            _pv_has_vol = (
                                "volume" in _pv_df.columns
                                and _pv_df["volume"].notna().any()
                                and _pv_df["volume"].sum() > 0
                            )

                            # ── Build figure ──────────────────────────────────
                            if _pv_has_vol:
                                _pv_fig = go.Figure()
                                _pv_fig.add_trace(go.Scatter(
                                    x=_pv_df.index, y=_pv_df["close"],
                                    mode="lines", line=dict(width=1.5, color="#4C78A8"),
                                    name="Close", yaxis="y1",
                                ))
                                _vol_max = _pv_df["volume"].max()
                                _pv_fig.add_trace(go.Bar(
                                    x=_pv_df.index, y=_pv_df["volume"],
                                    name="Volume", yaxis="y2",
                                    marker_color="rgba(100,100,200,0.18)",
                                    showlegend=False,
                                ))
                                _pv_fig.update_layout(
                                    yaxis2=dict(
                                        overlaying="y", side="right",
                                        range=[0, _vol_max * 5],
                                        showgrid=False, showticklabels=False,
                                    ),
                                )
                            else:
                                _pv_fig = go.Figure(go.Scatter(
                                    x=_pv_df.index, y=_pv_df["close"],
                                    mode="lines", line=dict(width=1.5, color="#4C78A8"),
                                    name="Close",
                                ))

                            # uirevision: stable key preserves Plotly zoom;
                            # changes when ↺ Scale is clicked → resets to layout range.
                            _pv_uirev = (
                                f"{_prev_ticker}_{_pv_range_sel}"
                                f"_{st.session_state.get('pv_rescale_n', 0)}"
                            )
                            _pv_fig.update_layout(
                                uirevision=_pv_uirev,
                                height=440,
                                margin=dict(l=0, r=0, t=6, b=0),
                                plot_bgcolor="white",
                                legend=dict(orientation="h", y=1.06, x=0),
                                xaxis=dict(
                                    showgrid=False,
                                    type="date",
                                    range=[str(_pv_win_start.date()),
                                           str(_pv_end_dt.date())],
                                    rangeslider=dict(
                                        visible=True,
                                        thickness=0.09,
                                        bgcolor=_PV_ORANGE_PALE,
                                        bordercolor=_PV_ORANGE,
                                        borderwidth=1,
                                        yaxis=dict(rangemode="auto"),
                                    ),
                                ),
                                yaxis=dict(
                                    showgrid=True,
                                    gridcolor="#eee",
                                    fixedrange=False,
                                    range=_pv_y_range,
                                ),
                            )
                            st.plotly_chart(_pv_fig, use_container_width=True)

                            # ── Last 20 rows table ────────────────────────────
                            with st.expander("🔎  Last 20 rows", expanded=False):
                                _pv_tail = _pv_df.tail(20).iloc[::-1].copy()
                                _pv_tail.index = _pv_tail.index.strftime("%Y-%m-%d")
                                _pv_tail.index.name = "Date"
                                _fmt_cols = {}
                                for _c in _pv_tail.columns:
                                    if _c == "volume":
                                        _pv_tail[_c] = _pv_tail[_c].apply(
                                            lambda v: f"{v:,.0f}" if pd.notna(v) else ""
                                        )
                                    else:
                                        _fmt_cols[_c] = st.column_config.NumberColumn(
                                            format="%.4f"
                                        )
                                st.dataframe(
                                    _pv_tail.reset_index(),
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config=_fmt_cols,
                                )
                    except Exception as _pv_e:
                        st.caption(f"Preview unavailable: {_pv_e}")

                # ── Manage ───────────────────────────────────────────────────
                st.divider()
                st.subheader("Manage")
                _mgmt_col1, _mgmt_col2 = st.columns(2)

                with _mgmt_col1:
                    st.markdown("**Reclassify**")
                    rc_t, rc_c, rc_b = st.columns([2, 2, 1])
                    with rc_t:
                        r_ticker = st.selectbox("Ticker", [a["ticker"] for a in assets],
                                                key="reclassify_ticker")
                    with rc_c:
                        r_class = st.selectbox(
                            "New class",
                            ["index", "equity", "fx", "crypto", "indicator", "other"],
                            key="reclassify_class",
                        )
                    with rc_b:
                        st.write("")
                        st.write("")
                        if st.button("✔  Apply", key="reclassify_btn"):
                            import subprocess
                            subprocess.run(
                                [sys.executable, "-m", "databank.updater", "reclassify",
                                 "--ticker", r_ticker, "--class", r_class],
                                capture_output=True, text=True,
                            )
                            _list_tickers.clear()
                            st.success(f"{r_ticker} → {r_class}")
                            st.rerun()

                with _mgmt_col2:
                    st.markdown("**Delete**")
                    st.caption("Permanently removes the asset from the catalog and deletes its data file.")
                    del_col1, del_col2 = st.columns([3, 1])
                    with del_col1:
                        del_ticker = st.selectbox("Asset to delete", [a["ticker"] for a in assets],
                                                  key="delete_ticker")
                    with del_col2:
                        st.write("")
                        st.write("")
                        if st.button("🗑 Delete", key="delete_btn", type="secondary"):
                            st.session_state["_asset_del_pending"] = del_ticker

                    if st.session_state.get("_asset_del_pending") == del_ticker:
                        st.warning(f"Delete **{del_ticker}** ? This cannot be undone.")
                        _adc1, _adc2 = st.columns([1, 1])
                        with _adc1:
                            if st.button("Yes, delete", key="asset_del_confirm", type="primary"):
                                from databank.catalog import delete as catalog_delete
                                parquet_path = catalog_delete(del_ticker)
                                if parquet_path is not None and parquet_path.exists():
                                    parquet_path.unlink()
                                _list_tickers.clear()
                                st.session_state.pop("_asset_del_pending", None)
                                st.session_state.pop("delete_ticker", None)
                                st.rerun()
                        with _adc2:
                            if st.button("Cancel", key="asset_del_cancel"):
                                st.session_state.pop("_asset_del_pending", None)
                                st.rerun()
            else:
                st.info("Data bank is empty.")
        except Exception as e:
            st.error(f"Error: {e}")

    with tab3:
        st.subheader("Import from a TradingView folder")
        st.caption(
            "Each CSV file in the folder becomes one asset — the filename is used as the ticker."
        )
        st.info(
            "**Daily mode only** — intraday files (hourly, minute, tick data) "
            "are not supported and will be rejected automatically.",
            icon="ℹ️",
        )

        tv_folder = st.text_input(
            "Folder path",
            value=st.session_state.get("tv_folder_path", ""),
            key="tv_folder_input",
            placeholder="C:/Users/you/Documents/TradingView exports",
            help="Paste the full path to the folder containing the exported CSV files.",
        )

        tv_role = st.selectbox(
            "Asset role",
            ["Indicator / metric", "Index (tradeable)", "Equity (tradeable)",
             "FX (tradeable)", "Crypto (tradeable)"],
            key="tv_role",
            help="How these assets will be classified in the catalog",
        )
        _TV_ROLE_MAP = {
            "Indicator / metric": "indicator",
            "Index (tradeable)":    "index",
            "Equity (tradeable)":   "equity",
            "FX (tradeable)":       "fx",
            "Crypto (tradeable)":   "crypto",
        }
        if st.button("📂  Import folder", key="tv_import_btn", type="primary"):
            if not tv_folder or not Path(tv_folder).exists():
                st.error(f"Folder not found: `{tv_folder}`")
            else:
                import subprocess
                with st.spinner("Importing…"):
                    r = subprocess.run(
                        [sys.executable, "-m", "databank.updater", "tv-import",
                         "--folder", tv_folder,
                         "--class", _TV_ROLE_MAP[tv_role]],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                    )
                st.code(r.stdout + r.stderr)
                if r.returncode == 0:
                    st.success("Import complete.")
                    st.rerun()

        with st.expander("What happens after import?", expanded=False):
            st.markdown(
                """
**Pipeline :**
1. Each CSV in the folder is read and column names are normalised
   (`Date / time → timestamp`, `open / high / low / close / volume`)
2. The series is deduplicated and sorted chronologically
3. Saved as **Parquet** → `DATASETS/{class}/{ticker}.parquet`
   (compressed, ~10× faster to read than CSV)
4. Registered in `DATASETS/_profiles/catalog.json` with metadata
   (date range, bar count, provider, currency…)

**After that, the asset is available :**
- **Run Backtest** → asset selector
- **Benchmark** → comparison chart
- **Build Strategy** → usable as condition operand or companion series
                """
            )

    with tab2:
        st.subheader("Import a single file")

        # ── Helper : détection rapide de la fréquence ─────────────────────────
        def _quick_freq_check(up) -> str:
            """Lit les 200 premières lignes pour détecter la fréquence."""
            import io as _io
            _ts_names = {
                "date", "datetime", "time", "timestamp", "ts",
                "<date>", "<datetime>", "<time>", "gmt time",
            }
            try:
                content = up.read()
                up.seek(0)
                # Excel
                if up.name.lower().endswith((".xlsx", ".xls")):
                    try:
                        _df = pd.read_excel(_io.BytesIO(content), nrows=200)
                        _tc = next((c for c in _df.columns if c.strip().lower() in _ts_names), None)
                        if _tc:
                            _dates = pd.to_datetime(_df[_tc], errors="coerce").dropna().sort_values()
                            if len(_dates) >= 3:
                                _h = _dates.diff().dropna().median().total_seconds() / 3600
                                return "intraday" if _h < 22 else ("daily" if _h < 60 else ("weekly" if _h < 300 else "monthly"))
                    except Exception:
                        pass
                    return "unknown"
                # CSV — teste plusieurs séparateurs
                for _sep in [",", ";", "\t", "|"]:
                    try:
                        _df = pd.read_csv(_io.BytesIO(content), sep=_sep, nrows=200,
                                          on_bad_lines="skip")
                        _tc = next((c for c in _df.columns if c.strip().lower() in _ts_names), None)
                        if _tc is None:
                            continue
                        _dates = pd.to_datetime(_df[_tc], errors="coerce").dropna().sort_values()
                        if len(_dates) < 3:
                            continue
                        _h = _dates.diff().dropna().median().total_seconds() / 3600
                        return "intraday" if _h < 22 else ("daily" if _h < 60 else ("weekly" if _h < 300 else "monthly"))
                    except Exception:
                        continue
            except Exception:
                pass
            return "unknown"

        # ── Upload via Streamlit (no file path needed) ────────────────────────
        uploaded = st.file_uploader(
            "Drop a CSV or Excel file here, or click to browse",
            type=["csv", "xlsx", "xls"],
            key="csv_uploader",
        )

        # Auto-fill ticker from filename + frequency check
        _freq_detected = "unknown"
        if uploaded is not None:
            _auto = Path(uploaded.name).stem.split(",")[0].split("_")[0].upper()
            if st.session_state.get("_last_upload") != uploaded.name:
                st.session_state["csv_ticker_val"] = _auto
                st.session_state["_last_upload"] = uploaded.name
                st.session_state.pop("_upload_freq", None)
            if "_upload_freq" not in st.session_state:
                st.session_state["_upload_freq"] = _quick_freq_check(uploaded)
            _freq_detected = st.session_state["_upload_freq"]
            if _freq_detected == "intraday":
                st.error(
                    "⛔ **Intraday data not supported** — sub-daily frequency detected "
                    "(hourly, minute or tick data).\n\n"
                    "This engine operates in **daily mode** only. "
                    "Please use daily, weekly, or monthly data."
                )
            elif _freq_detected in ("weekly", "monthly"):
                st.info(
                    f"**{_freq_detected.capitalize()} data detected** — will be automatically "
                    "resampled to daily frequency (forward-fill) before saving.",
                    icon="ℹ️",
                )

        # ── Ticker + role + metadata ──────────────────────────────────────────
        csv_r1c1, csv_r1c2 = st.columns([2, 4])
        with csv_r1c1:
            csv_ticker = st.text_input(
                "Ticker  (e.g. AAPL)",
                value=st.session_state.get("csv_ticker_val", ""),
                key="csv_ticker",
            ).strip().upper()
        with csv_r1c2:
            csv_role = st.selectbox(
                "Asset role",
                ["Indicator / metric", "Index (tradeable)", "Equity (tradeable)",
                 "FX (tradeable)", "Crypto (tradeable)", "Other"],
                key="csv_role",
            )

        csv_r2c1, csv_r2c2 = st.columns([4, 1])
        with csv_r2c1:
            csv_name = st.text_input("Full name (optional)", key="csv_name").strip()
        with csv_r2c2:
            csv_currency = st.text_input("Currency", value="USD", key="csv_currency").strip().upper() or "USD"

        _CSV_ROLE_MAP = {
            "Indicator / metric": "indicator",
            "Index (tradeable)":    "index",
            "Equity (tradeable)":   "equity",
            "FX (tradeable)":       "fx",
            "Crypto (tradeable)":   "crypto",
            "Other":                "other",
        }
        if st.button("📥  Import file", key="csv_import_btn", type="primary",
                     disabled=(_freq_detected == "intraday")):
            if uploaded is None:
                st.error("Please select a file first.")
            elif not csv_ticker:
                st.error("Please enter a ticker symbol.")
            else:
                import subprocess, tempfile
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as _tmp:
                    _tmp.write(uploaded.read())
                    _tmp_path = _tmp.name
                cmd = [sys.executable, "-m", "databank.updater", "import",
                       "--file", _tmp_path,
                       "--ticker", csv_ticker,
                       "--name", csv_name or csv_ticker,
                       "--class", _CSV_ROLE_MAP[csv_role],
                       "--currency", csv_currency,
                       "--non-interactive"]
                with st.spinner("Importing…"):
                    r = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace",
                        cwd=str(Path(__file__).parent),
                    )
                Path(_tmp_path).unlink(missing_ok=True)
                st.code(r.stdout + r.stderr)
                if r.returncode == 0:
                    st.success(f"**{csv_ticker}** imported — available in all pages.")
                    st.session_state.pop("csv_ticker_val", None)
                    st.session_state.pop("_last_upload", None)
                    st.rerun()

        with st.expander("What happens after import?", expanded=False):
            st.markdown(
                """
**Pipeline :**
1. The file is read — separator auto-detected, column names normalised
   (`Date / time → timestamp`, `open / high / low / close / volume`)
2. Deduplicated and sorted chronologically
3. Saved as **Parquet** → `DATASETS/{class}/{ticker}.parquet`
   (compressed, ~10× faster to read than CSV)
4. Registered in `DATASETS/_profiles/catalog.json` with metadata
   (date range, bar count, provider, currency…)

**After that, the asset is available :**
- **Run Backtest** → asset selector
- **Benchmark** → comparison chart
- **Build Strategy** → usable as condition operand or companion series

Re-importing the same ticker **merges** the new bars with the existing ones
(no duplicates — new data extends the history).
                """
            )

    with tab4:
        # ── Yahoo Finance ──────────────────────────────────────────────────────
        st.subheader("Download from Yahoo Finance")
        st.caption("Stocks · ETFs · Indices · FX · Crypto — no API key required")

        # ── Constantes ────────────────────────────────────────────────────────
        _YF_UNIT_AUTO = "Auto (from Yahoo metadata)"
        _YF_UNIT_OPTIONS = [
            _YF_UNIT_AUTO,
            "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
            "% (rate / yield)", "Index value",
            "Thousands USD", "Millions USD", "Billions USD", "Other",
        ]
        _YF_ROLES = {
            "Tradeable equity":        "equity",
            "Tradeable index":         "index",
            "FX (currency pair)":      "fx",
            "Crypto":                  "crypto",
            "Volatility / Indicator":  "indicator",
            "Other":                   "other",
        }

        # preset → (yahoo_ticker, databank_name, unit, role_label)
        _YF_PRESETS: dict[str, tuple[str, str, str, str]] = {
            "— Custom —":             ("",          "",        "",                   "Tradeable equity"),
            # ── US Indices ────────────────────────────────────────────────────
            "S&P 500":                ("^GSPC",     "SPX",     "Index value",        "Tradeable index"),
            "Nasdaq 100":             ("^NDX",      "NDX",     "Index value",        "Tradeable index"),
            "Dow Jones":              ("^DJI",      "DJI",     "Index value",        "Tradeable index"),
            "Russell 2000":           ("^RUT",      "RUT",     "Index value",        "Tradeable index"),
            # ── Global indices ────────────────────────────────────────────────
            "DAX (Germany)":          ("^GDAXI",    "DAX",     "Index value",        "Tradeable index"),
            "CAC 40 (France)":        ("^FCHI",     "CAC40",   "Index value",        "Tradeable index"),
            "FTSE 100 (UK)":          ("^FTSE",     "FTSE",    "Index value",        "Tradeable index"),
            "Nikkei 225 (Japan)":     ("^N225",     "NKY",     "Index value",        "Tradeable index"),
            "Hang Seng (HK)":         ("^HSI",      "HSI",     "Index value",        "Tradeable index"),
            # ── Volatility ────────────────────────────────────────────────────
            "VIX":                    ("^VIX",      "VIX",     "Index value",        "Volatility / Indicator"),
            "VIX 3-Month":            ("^VIX3M",    "VIX3M",   "Index value",        "Volatility / Indicator"),
            # ── Commodities ETF ───────────────────────────────────────────────
            "Gold ETF (GLD)":         ("GLD",       "GLD",     "USD",                "Tradeable index"),
            "Silver ETF (SLV)":       ("SLV",       "SLV",     "USD",                "Tradeable index"),
            "Oil ETF (USO)":          ("USO",       "USO",     "USD",                "Tradeable index"),
            # ── Bond ETF ──────────────────────────────────────────────────────
            "20Y Treasury ETF (TLT)": ("TLT",       "TLT",     "USD",                "Tradeable index"),
            "Short-Term Bond (SHY)":  ("SHY",       "SHY",     "USD",                "Tradeable index"),
            # ── FX ────────────────────────────────────────────────────────────
            "EUR/USD":                ("EURUSD=X",  "EURUSD",  "USD",                "FX (currency pair)"),
            "GBP/USD":                ("GBPUSD=X",  "GBPUSD",  "USD",                "FX (currency pair)"),
            "USD/JPY":                ("USDJPY=X",  "USDJPY",  "JPY",                "FX (currency pair)"),
            # ── Crypto ────────────────────────────────────────────────────────
            "Bitcoin":                ("BTC-USD",   "BTCUSD",  "USD",                "Crypto"),
            "Ethereum":               ("ETH-USD",   "ETHUSD",  "USD",                "Crypto"),
        }

        # ── Auto-fill via session_state quand le preset change ─────────────────
        _yf_preset = st.selectbox(
            "Common tickers (or choose Custom)",
            list(_YF_PRESETS.keys()),
            key="yf_preset",
        )
        if _yf_preset == "— Custom —":
            st.caption(
                "Enter the Yahoo Finance ticker below — find it at "
                "[finance.yahoo.com](https://finance.yahoo.com) "
                "(e.g. `AAPL`, `^GSPC`, `BTC-USD`, `EURUSD=X`)."
            )

        _yf_combo = _yf_preset
        if st.session_state.get("_yf_combo") != _yf_combo:
            st.session_state["_yf_combo"] = _yf_combo
            _ps_yt, _ps_name, _ps_unit, _ps_role = _YF_PRESETS[_yf_preset]
            st.session_state["yf_ticker_input"] = _ps_yt
            st.session_state["yf_name_input"]   = _ps_name
            st.session_state["yf_unit"]         = _ps_unit if _ps_unit else _YF_UNIT_AUTO
            st.session_state["yf_role"]         = _ps_role
            st.session_state.pop("_yf_validated_info", None)
            st.session_state.pop("_yf_import_result",  None)

        # ── Champs texte ───────────────────────────────────────────────────────
        _yf_t_col, _yf_name_col = st.columns([2, 2])
        with _yf_t_col:
            _yf_ticker = st.text_input(
                "Yahoo ticker",
                key="yf_ticker_input",
                placeholder="e.g. AAPL, ^GSPC, BTC-USD",
            ).strip().upper()
        with _yf_name_col:
            _yf_name = st.text_input(
                "Ticker name in databank",
                key="yf_name_input",
                placeholder="e.g. SPX",
            ).strip().upper()

        # ── Rôle + Unité ──────────────────────────────────────────────────────
        _yf_role_col, _yf_unit_col = st.columns([3, 2])
        with _yf_role_col:
            _yf_role = st.selectbox(
                "Asset role",
                list(_YF_ROLES.keys()),
                key="yf_role",
            )
        with _yf_unit_col:
            _yf_unit = st.selectbox(
                "Unit / Currency",
                _YF_UNIT_OPTIONS,
                key="yf_unit",
            )

        # ── Dates optionnelles ─────────────────────────────────────────────────
        with st.expander("Date range (optional — leave empty for full history)"):
            _yf_d1, _yf_d2 = st.columns(2)
            with _yf_d1:
                _yf_from = st.text_input(
                    "From (YYYY-MM-DD)", key="yf_from",
                    placeholder="e.g. 2010-01-01",
                ).strip() or None
            with _yf_d2:
                _yf_to = st.text_input(
                    "To (YYYY-MM-DD)", key="yf_to",
                    placeholder="leave empty = today",
                ).strip() or None

        # ── Info validée persistante ───────────────────────────────────────────
        if "_yf_validated_info" in st.session_state:
            _vi = st.session_state["_yf_validated_info"]
            _vi_line = f"**{_vi.get('name', _yf_ticker)}**"
            if _vi.get("exchange"): _vi_line += f"  |  Exchange: {_vi['exchange']}"
            if _vi.get("currency"): _vi_line += f"  |  Currency: {_vi['currency']}"
            if _vi.get("sector"):   _vi_line += f"  |  Sector: {_vi['sector']}"
            if _vi.get("type"):     _vi_line += f"  |  Type: {_vi['type']}"
            st.info(_vi_line)

        # ── Boutons Update infos + Import ──────────────────────────────────────
        _yf_val_col, _yf_imp_col = st.columns([1, 1])
        with _yf_val_col:
            if st.button("🔍  Update infos", key="yf_validate_btn"):
                if not _yf_ticker:
                    st.error("Please enter a Yahoo ticker.")
                else:
                    try:
                        import yfinance as _yf
                        _info = _yf.Ticker(_yf_ticker).info
                        st.session_state["_yf_validated_info"] = {
                            "name":     _info.get("longName") or _info.get("shortName") or _yf_ticker,
                            "exchange": _info.get("exchange", ""),
                            "currency": _info.get("currency", ""),
                            "sector":   _info.get("sector", ""),
                            "type":     _info.get("quoteType", ""),
                        }
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Ticker not found or yfinance error: {_e}")

        with _yf_imp_col:
            _yf_do_import = st.button("📥  Import", key="yf_import_btn", type="primary")

        # Confirmation d'écrasement
        if _yf_do_import:
            if not _yf_ticker:
                st.error("Please enter a Yahoo ticker.")
            elif not _yf_name:
                st.error("Please enter a databank name.")
            else:
                from databank.catalog import get as _cget_yf
                if _cget_yf(_yf_name):
                    st.session_state["_yf_overwrite_pending"] = _yf_name
                else:
                    st.session_state["_yf_overwrite_pending"] = None
                    st.session_state["_yf_confirmed"] = True
                st.rerun()

        if st.session_state.get("_yf_overwrite_pending"):
            _ow = st.session_state["_yf_overwrite_pending"]
            st.info(f"**{_ow}** already exists in the databank. New data will be **merged** with existing bars (no data loss).")
            _ow_y, _ow_n = st.columns([1, 1])
            with _ow_y:
                if st.button("Yes, merge & update", key="yf_overwrite_yes", type="primary"):
                    st.session_state["_yf_overwrite_pending"] = None
                    st.session_state["_yf_confirmed"] = True
                    st.rerun()
            with _ow_n:
                if st.button("Cancel", key="yf_overwrite_no"):
                    st.session_state["_yf_overwrite_pending"] = None
                    st.rerun()

        if st.session_state.pop("_yf_confirmed", False):
            try:
                from databank.providers.yfinance_provider import YFinanceProvider
                from databank.normalizer import DataNormalizer
                from databank import catalog as _cat
                from datetime import datetime as _dt

                _prov = YFinanceProvider()
                _norm = DataNormalizer()
                _start_dt = _dt.strptime(_yf_from, "%Y-%m-%d") if _yf_from else None
                _end_dt   = _dt.strptime(_yf_to,   "%Y-%m-%d") if _yf_to   else None

                with st.spinner(f"Downloading {_yf_ticker}…"):
                    _df = _prov.fetch(_yf_ticker, start=_start_dt, end=_end_dt)

                    try:
                        import yfinance as _yf2
                        _yf_info2  = _yf2.Ticker(_yf_ticker).info
                        _full_name = (_yf_info2.get("longName")
                                      or _yf_info2.get("shortName") or _yf_name)
                        _yf_meta_currency = _yf_info2.get("currency", "USD")
                    except Exception:
                        _full_name        = _yf_name
                        _yf_meta_currency = "USD"

                    # Résoudre "Auto" depuis les métadonnées Yahoo
                    if _yf_unit == _YF_UNIT_AUTO:
                        _unit_stored = _yf_meta_currency  # ex: "USD", "EUR"
                    else:
                        _unit_stored = _yf_unit

                    _asset_class = _YF_ROLES[_yf_role]
                    _yf_src_meta = {"provider": "yfinance", "currency": _unit_stored,
                                    "asset_class": _asset_class, "ticker": _yf_name,
                                    "yf_ticker": _yf_ticker}
                    _existing_yf = _norm.load_parquet(_yf_name, Path("DATASETS"))
                    if _existing_yf is not None:
                        # Fusion : existant en premier, nouveau en dernier → nouveau gagne (prix ajustés)
                        _merged_yf = pd.concat([_existing_yf, _df])
                        _merged_yf = _merged_yf[~_merged_yf.index.duplicated(keep="last")]
                        _merged_yf = _merged_yf.sort_index()
                        _df = _merged_yf
                    _norm.save_parquet(_df, _yf_name, _asset_class, Path("DATASETS"),
                                       source_meta=_yf_src_meta)
                    _cat.register(
                        ticker=_yf_name,
                        name=_full_name,
                        asset_class=_asset_class,
                        currency=_unit_stored,
                        provider="yfinance",
                        df=_df,
                    )
                    _list_tickers.clear()

                st.session_state["_yf_import_result"] = {
                    "ticker":    _yf_name,
                    "yf_ticker": _yf_ticker,
                    "name":      _full_name,
                    "role":      _yf_role,
                    "unit":      _unit_stored,
                    "unit_auto": _yf_unit == _YF_UNIT_AUTO,
                    "n_bars":    len(_df),
                    "date_start": str(_df.index.min().date()),
                    "date_end":   str(_df.index.max().date()),
                }
                st.rerun()

            except Exception as _e:
                st.error(f"Download failed: {_e}")

        # ── Résumé d'import persistant ─────────────────────────────────────────
        if "_yf_import_result" in st.session_state:
            _r = st.session_state["_yf_import_result"]
            st.success(f"✓ **{_r['ticker']}** imported successfully")
            with st.expander("Import summary", expanded=True):
                _c1, _c2 = st.columns(2)
                with _c1:
                    st.markdown(f"**Yahoo ticker** : `{_r['yf_ticker']}`")
                    st.markdown(f"**Name** : {_r['name']}")
                    st.markdown(f"**Saved as** : `{_r['ticker']}`")
                    st.markdown(f"**Asset role** : {_r['role']}")
                    st.markdown(f"**Unit** : {_r['unit']}"
                                + ("  *(from Yahoo metadata)*" if _r["unit_auto"] else ""))
                with _c2:
                    st.markdown(f"**Bars downloaded** : {_r['n_bars']:,}")
                    st.markdown(f"**Date range** : {_r['date_start']} → {_r['date_end']}")

        st.divider()

        # ── Update existing Yahoo assets ───────────────────────────────────────
        st.subheader("Update existing assets")
        try:
            from databank import catalog as _cat2
            from databank.normalizer import DataNormalizer as _DN2
            _yf_assets = [
                e for e in _cat2.list_assets()
                if e.get("provider") in ("yfinance", "yahoo")
            ]
        except Exception:
            _yf_assets = []

        if not _yf_assets:
            st.caption("No Yahoo Finance assets in the databank yet.")
        else:
            _upd_df = pd.DataFrame(_yf_assets)[["ticker", "name", "end", "n_bars"]]
            _upd_df.columns = ["Ticker", "Name", "Last bar", "Bars"]
            st.dataframe(_upd_df, use_container_width=True, hide_index=True)

            if st.button("🔄  Update all", key="yf_update_all_btn", type="primary"):
                _errors = []
                for _asset in _yf_assets:
                    try:
                        from databank.providers.yfinance_provider import YFinanceProvider
                        from databank.normalizer import DataNormalizer
                        from databank import catalog as _cat3
                        from datetime import datetime as _dt2

                        _t         = _asset["ticker"]
                        _start_upd = _dt2.strptime(_asset["end"], "%Y-%m-%d")

                        with st.spinner(f"Updating {_t}…"):
                            _new  = YFinanceProvider().fetch(_t, start=_start_upd)
                            _norm2 = DataNormalizer()
                            _norm2.update_parquet(_t, _new, _asset["class"], Path("DATASETS"))
                            _full = _norm2.load_parquet(_t, Path("DATASETS"))
                            _cat3.register(
                                _t, _asset["name"], _asset["class"],
                                _asset.get("currency", "USD"), "yfinance", _full,
                            )
                    except Exception as _ue:
                        _errors.append(f"{_asset['ticker']}: {_ue}")
                if _errors:
                    st.error("\n".join(_errors))
                else:
                    _list_tickers.clear()
                    st.success("All assets updated.")
                    st.rerun()

        st.divider()

        # ── Maintenance yfinance ───────────────────────────────────────────────
        st.subheader("Library")
        try:
            import yfinance as _yf_check
            _yf_ver = _yf_check.__version__
        except ImportError:
            _yf_ver = None

        if _yf_ver:
            st.caption(f"yfinance installed : **{_yf_ver}**")
        else:
            st.warning("yfinance is not installed — run: `pip install yfinance`")

        with st.expander("⚠️  Imports broken? Update yfinance", expanded=False):
            st.markdown(
                "**Why update yfinance?**  \n"
                "Yahoo Finance occasionally changes its API structure without notice. "
                "When that happens, downloads may fail or return empty data. "
                "The open-source community usually ships a fix within a few days as a new library version.  \n\n"
                "**When to use this?**  \n"
                "If you see errors like *No data found*, *JSONDecodeError*, *KeyError: 'Close'*… "
                "upgrading to the latest version usually fixes the issue.  \n\n"
                "A restart of the app is required after the update."
            )
            if st.button("Upgrade yfinance now", key="yf_upgrade_btn", type="primary"):
                import subprocess as _sp
                with st.spinner("Upgrading yfinance…"):
                    _r = _sp.run(
                        [sys.executable, "-m", "pip", "install", "--upgrade", "yfinance"],
                        capture_output=True, text=True,
                    )
                if _r.returncode == 0:
                    st.success("yfinance upgraded. Restart the app to apply the changes.")
                else:
                    st.error(_r.stderr[-500:] if _r.stderr else "Upgrade failed.")

    with tab5:
        st.subheader("Import from FRED / ALFRED")
        st.caption(
            "FRED = latest revision  |  ALFRED = first publication (no look-ahead bias)"
        )

        # ── Cle API ────────────────────────────────────────────────────────────
        from databank.fred_config import get_api_key, set_api_key, is_configured

        _fred_key_saved = get_api_key() or ""
        with st.expander(
            "🔑  API Key" + ("  ✅" if is_configured() else "  ⚠️  Required"),
            expanded=not is_configured(),
        ):
            _new_key = st.text_input(
                "FRED API key",
                value=_fred_key_saved,
                type="password",
                key="fred_api_key_input",
                help="Free key — register at fred.stlouisfed.org/docs/api/api_key.html",
            )
            col_save, col_link = st.columns([1, 3])
            with col_save:
                if st.button("💾  Save key", key="fred_save_key"):
                    if _new_key.strip():
                        set_api_key(_new_key.strip())
                        st.success("Key saved.")
                        st.rerun()
                    else:
                        st.error("Please enter a key.")
            with col_link:
                st.markdown(
                    "[Get a free FRED API key →](https://fred.stlouisfed.org/docs/api/api_key.html)"
                )

        if not is_configured():
            st.stop()

        api_key = get_api_key()

        # ── Presets serie : (series_id, ticker, unit, role) ──────────────────────
        _UNIT_AUTO    = "Auto (from FRED metadata)"
        _UNIT_OPTIONS = [
            _UNIT_AUTO,
            "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
            "% (rate / yield)", "Index value",
            "Thousands USD", "Millions USD", "Billions USD", "Other",
        ]
        _FRED_ROLES = {
            "Macro / Economic data":       "indicator",   # CPI, GDP, PMI...
            "Rate / Yield":                "indicator",   # Fed Funds, treasuries
            "Currency (FX) index":         "fx",          # DXY
            "Market breadth / Volatility": "indicator",   # VIX, A/D line...
            "Tradeable index":             "index",       # rare sur FRED
            "Tradeable equity":            "equity",
            "Other":                       "other",
        }
        _FRED_PRESETS = {
            # label:                  (series_id,   ticker,    unit,                  role)
            "— Custom —":             ("",          "",        "",                    "Macro / Economic data"),
            "CPI (All Urban)":        ("CPIAUCSL",  "CPI",     "Index value",         "Macro / Economic data"),
            "Core CPI (ex F&E)":      ("CPILFESL",  "CPIC",    "Index value",         "Macro / Economic data"),
            "PCE Inflation":          ("PCEPI",     "PCE",     "Index value",         "Macro / Economic data"),
            "GDP (Nominal, Qtrly)":   ("GDP",       "GDP",     "Billions USD",        "Macro / Economic data"),
            "Unemployment Rate":      ("UNRATE",    "UNRATE",  "% (rate / yield)",    "Macro / Economic data"),
            "Fed Funds Rate":         ("FEDFUNDS",  "FFR",     "% (rate / yield)",    "Rate / Yield"),
            "10Y Treasury Yield":     ("DGS10",     "TNX",     "% (rate / yield)",    "Rate / Yield"),
            "2Y Treasury Yield":      ("DGS2",      "TWO",     "% (rate / yield)",    "Rate / Yield"),
            "Yield Spread 10Y-2Y":    ("T10Y2Y",    "SPREAD",  "% (rate / yield)",    "Rate / Yield"),
            "US Dollar Index (Broad)":("DTWEXBGS",  "DXY",     "Index value",         "Currency (FX) index"),
            "Initial Jobless Claims": ("ICSA",      "CLAIMS",  "Thousands USD",       "Macro / Economic data"),
            "Consumer Confidence":    ("UMCSENT",   "UMCSENT", "Index value",         "Macro / Economic data"),
            "Industrial Production":  ("INDPRO",    "INDPRO",  "Index value",         "Macro / Economic data"),
        }

        _preset_col, _mode_col = st.columns([3, 2])
        with _preset_col:
            _preset = st.selectbox(
                "Common series (or choose Custom)",
                list(_FRED_PRESETS.keys()),
                key="fred_preset",
            )
        with _mode_col:
            _mode = st.selectbox(
                "Mode",
                ["First publication (ALFRED)", "Latest revision (FRED)"],
                key="fred_mode",
                help=(
                    "First publication: uses the date the value was first publicly available "
                    "(ALFRED vintage). Eliminates look-ahead bias.\n\n"
                    "Latest revision: uses the reference date (e.g. Jan 1 for January CPI) "
                    "with the most recent revised value."
                ),
            )
        _mode_key    = "first" if "First" in _mode else "latest"
        _mode_suffix = "PRELIM" if _mode_key == "first" else "REVISED"

        # ── Warning + date shift (FRED mode only) ─────────────────────────────
        if _mode_key == "latest":
            st.warning(
                "**FRED mode: dates are reference dates, not publication dates.**  \n"
                "Example: January CPI is dated `2024-01-01` but was only published on `2024-02-13`.  \n"
                "Shifting dates forward reduces look-ahead bias.",
                icon="⚠️",
            )
            _shift_bars = st.number_input(
                "Shift dates forward by N business days (0 = no shift)",
                min_value=0, max_value=120, step=1,
                key="fred_shift_bars",
                help=(
                    "0 = raw FRED reference dates (start of reference period)\n"
                    "Typical values:\n"
                    "• Monthly (CPI, UNRATE…): 20–30 days\n"
                    "• Quarterly (GDP…): 30–45 days\n"
                    "• Weekly (Claims…): 5–7 days"
                ),
            )
        else:
            _shift_bars = 0

        # ── Transformation ─────────────────────────────────────────────────────
        # label → (code API FRED, suffixe ticker)
        _FRED_TRANSFORMS: dict[str, tuple[str, str]] = {
            "Level (raw data)":              ("lin", ""),
            "% Change YoY (year-over-year)": ("pc1", "_YOY"),
            "% Change MoM / period":         ("pch", "_MOM"),
            "Change YoY — absolute":         ("ch1", "_CH1"),
            "Change MoM / period — absolute":("chg", "_CHG"),
        }
        _transform_label = st.selectbox(
            "Transformation",
            list(_FRED_TRANSFORMS.keys()),
            key="fred_transform",
            help=(
                "Applied server-side by FRED before delivery.\n"
                "Level = raw index value (e.g. CPI = 308.4)\n"
                "% Change YoY = year-over-year inflation rate\n"
                "% Change MoM = month-over-month change"
            ),
        )
        _transform_code, _transform_sfx = _FRED_TRANSFORMS[_transform_label]

        # ── Auto-fill Series ID + Ticker via session_state ─────────────────────
        _combo = f"{_preset}|{_mode_key}|{_transform_code}"

        def _map_fred_units(u: str) -> str:
            """Mappe les unités FRED vers les options du selectbox."""
            ul = u.lower()
            if any(x in ul for x in ("percent change", "percent chg", "pct chg")):
                return "% (rate / yield)"
            if any(x in ul for x in ("percent", "rate", "yield", "ratio")):
                return "% (rate / yield)"
            if "billions" in ul:
                return "Billions USD"
            if "millions" in ul:
                return "Millions USD"
            if "thousands" in ul:
                return "Thousands USD"
            if "index" in ul:
                return "Index value"
            if any(x in ul for x in ("dollar", "usd", "$")):
                return "USD"
            return "Other"

        _all_known_sfx = ["_PRELIM", "_REVISED", "_YOY", "_MOM", "_CH1", "_CHG",
                          "_1ST", "_REV"]

        if st.session_state.get("_fred_combo") != _combo:
            _prev_combo = st.session_state.get("_fred_combo", "")
            st.session_state["_fred_combo"] = _combo
            _ps, _pt, _p_unit, _p_role = _FRED_PRESETS[_preset]
            _full_sfx = f"{_transform_sfx}_{_mode_suffix}" if _transform_sfx else f"_{_mode_suffix}"
            # Unité selon la transformation (priorité sur l'unité du preset)
            if _transform_code in ("pc1", "pch"):
                _effective_unit = "% (rate / yield)"
            elif _transform_code in ("ch1", "chg"):
                _effective_unit = _p_unit or "Other"   # variation absolue = mêmes unités que le raw
            else:
                _effective_unit = _p_unit or ""         # level = unité native

            if _preset != "— Custom —":
                # Preset connu → tout mettre à jour
                st.session_state["fred_series_id"] = _ps
                st.session_state["fred_ticker"]    = f"{_pt}{_full_sfx}"
                if _effective_unit in _UNIT_OPTIONS:
                    st.session_state["fred_currency"] = _effective_unit
                if _p_role in _FRED_ROLES:
                    st.session_state["fred_role"] = _p_role
            else:
                # Custom : reconstruire le suffixe du ticker + mettre à jour l'unité
                _cur_t = st.session_state.get("fred_ticker", "")
                for _s in sorted(_all_known_sfx, key=len, reverse=True):
                    while _cur_t.endswith(_s):
                        _cur_t = _cur_t[: -len(_s)]
                if _cur_t:
                    st.session_state["fred_ticker"] = f"{_cur_t}{_full_sfx}"
                # Si on vient de basculer vers Custom → reset l'unité sur "Auto"
                _prev_preset = _prev_combo.split("|")[0] if "|" in _prev_combo else ""
                if _prev_preset != "— Custom —":
                    st.session_state["fred_currency"] = _UNIT_AUTO
                # Si transform devient %, on peut quand même auto-remplir
                elif _transform_code in ("pc1", "pch"):
                    st.session_state["fred_currency"] = "% (rate / yield)"
            # Effacer l'info validée quand le series ID change
            if _prev_combo.split("|")[0] != _combo.split("|")[0]:
                st.session_state.pop("_fred_validated_info", None)
                st.session_state.pop("_fred_import_result", None)
                st.session_state.pop("_fred_preview_df", None)

        if _preset == "— Custom —":
            st.caption(
                "Enter the exact FRED Series ID below — "
                "find it at [fred.stlouisfed.org](https://fred.stlouisfed.org) "
                "(e.g. `CPIAUCSL`, `UNRATE`, `DGS10`)."
            )

        _sid_col, _tick_col = st.columns([2, 2])
        with _sid_col:
            _series_id = st.text_input(
                "FRED Series ID",
                key="fred_series_id",
                placeholder="e.g. CPIAUCSL",
            ).strip().upper()
        with _tick_col:
            _ticker_val = st.text_input(
                "Ticker name in databank",
                key="fred_ticker",
                placeholder="e.g. CPI_PRELIM",
            ).strip().upper()

        _role_col, _curr_col = st.columns([3, 2])
        with _role_col:
            _fred_role = st.selectbox(
                "Asset role",
                list(_FRED_ROLES.keys()),
                key="fred_role",
            )
        with _curr_col:
            _fred_currency = st.selectbox(
                "Unit / Currency",
                _UNIT_OPTIONS,
                key="fred_currency",
            )

        # ── Info validée persistante ───────────────────────────────────────────
        if "_fred_validated_info" in st.session_state:
            _vi = st.session_state["_fred_validated_info"]
            st.info(
                f"**{_vi.get('title', _series_id)}**  |  "
                f"Frequency: {_vi.get('frequency', '?')}  |  "
                f"Units: {_vi.get('units', '?')}  |  "
                f"Source: {_vi.get('source', '?')}  |  "
                f"Updated: {_vi.get('last_updated', '?')[:10]}"
            )

        # ── Preview décalage de date (FRED mode uniquement) ───────────────────
        if _mode_key == "latest" and _series_id:
            if st.button("👁  Preview date shift", key="fred_preview_btn"):
                try:
                    from databank.providers.fred_provider import FREDProvider as _FP
                    _pv_raw = _FP().fetch(
                        _series_id, mode="latest", api_key=api_key,
                        start_date="2022-01-01", end_date="2023-06-30",
                        units="lin",
                    )
                    st.session_state["_fred_preview_df"] = _pv_raw.iloc[::max(1, len(_pv_raw)//8)][:8]
                except Exception as _pv_e:
                    st.error(f"Preview fetch failed : {_pv_e}")

            if "_fred_preview_df" in st.session_state:
                import pandas as _pd_pv
                _pv = st.session_state["_fred_preview_df"].copy()
                _shift_label = f"+{int(_shift_bars)} bdays" if _shift_bars else "none"
                _pv_rows = []
                for _dt, _row in _pv.iterrows():
                    _shifted = (_dt + _pd_pv.offsets.BDay(int(_shift_bars))) if _shift_bars > 0 else _dt
                    _pv_rows.append({
                        "Original date (FRED)": str(_dt.date()),
                        f"Shifted date ({_shift_label})": str(_shifted.date()),
                        "Value": round(float(_row["close"]), 4),
                    })
                st.caption(f"Preview — {len(_pv_rows)} observations — `{_series_id}`")
                st.dataframe(_pd_pv.DataFrame(_pv_rows), use_container_width=True, hide_index=True)

        # ── Bouton Validate ────────────────────────────────────────────────────
        _val_col, _imp_col = st.columns([1, 1])
        with _val_col:
            if st.button("🔍  Update infos", key="fred_validate_btn"):
                if not _series_id:
                    st.error("Please enter a FRED Series ID.")
                else:
                    try:
                        from databank.providers.fred_provider import FREDProvider
                        _info = FREDProvider().get_series_info(_series_id, api_key)
                        st.session_state["_fred_validated_info"] = _info
                        # Auto-fill unité — respecte la transformation active
                        if _transform_code in ("pc1", "pch"):
                            # Transformation % : l'unité est toujours % quelle que soit la série
                            st.session_state["fred_currency"] = "% (rate / yield)"
                        else:
                            # Level ou variation absolue : on mappe depuis les métadonnées FRED
                            _unit_raw    = _info.get("units", "")
                            _unit_mapped = _map_fred_units(_unit_raw)
                            if _unit_mapped in _UNIT_OPTIONS:
                                st.session_state["fred_currency"] = _unit_mapped
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Series not found or API error: {_e}")

        # ── Bouton Import ──────────────────────────────────────────────────────
        with _imp_col:
            _do_import = st.button("📥  Import series", key="fred_import_btn", type="primary")

        # Confirmation d'écrasement
        if _do_import:
            if not _series_id:
                st.error("Please enter a FRED Series ID.")
            elif not _ticker_val:
                st.error("Please enter a ticker name.")
            else:
                from databank.catalog import get as _cget_check
                if _cget_check(_ticker_val):
                    st.session_state["_fred_overwrite_pending"] = _ticker_val
                else:
                    st.session_state["_fred_overwrite_pending"] = None
                    st.session_state["_fred_confirmed"] = True
                st.rerun()

        if st.session_state.get("_fred_overwrite_pending"):
            _ow_ticker = st.session_state["_fred_overwrite_pending"]
            st.info(
                f"**{_ow_ticker}** already exists in the databank. "
                "New data will be **merged** with existing bars (no data loss)."
            )
            _ow_yes, _ow_no = st.columns([1, 1])
            with _ow_yes:
                if st.button("Yes, merge & update", key="fred_overwrite_yes", type="primary"):
                    st.session_state["_fred_overwrite_pending"] = None
                    st.session_state["_fred_confirmed"] = True
                    st.rerun()
            with _ow_no:
                if st.button("Cancel", key="fred_overwrite_no"):
                    st.session_state["_fred_overwrite_pending"] = None
                    st.rerun()

        if st.session_state.pop("_fred_confirmed", False):
            if not _series_id:
                st.error("Please enter a FRED Series ID.")
            elif not _ticker_val:
                st.error("Please enter a ticker name.")
            else:
                try:
                    from databank.providers.fred_provider import FREDProvider
                    from databank.normalizer import DataNormalizer
                    from databank.analyzer import detect_frequency
                    from databank import catalog as _cat

                    _provider   = FREDProvider()
                    _normalizer = DataNormalizer()

                    with st.spinner(f"Fetching {_series_id} ({_transform_label}) from FRED…"):
                        # Métadonnées série (toujours fetchées — nécessaires pour résoudre "Auto")
                        _sinfo = {}
                        try:
                            _sinfo       = _provider.get_series_info(_series_id, api_key)
                            _series_name = _sinfo.get("title", _ticker_val)
                            if _transform_code != "lin":
                                _series_name += f" [{_transform_label}]"
                        except Exception:
                            _series_name = _ticker_val

                        # Résoudre l'unité "Auto" depuis les métadonnées
                        if _fred_currency == _UNIT_AUTO:
                            _raw_units   = _sinfo.get("units", "")
                            _fred_currency_stored = _map_fred_units(_raw_units) if _raw_units else "Other"
                        else:
                            _fred_currency_stored = _fred_currency

                        _df = _provider.fetch(
                            series_id=_series_id,
                            mode=_mode_key,
                            api_key=api_key,
                            units=_transform_code,
                        )

                        # Décalage de date (FRED mode uniquement)
                        if _mode_key == "latest" and _shift_bars > 0:
                            import pandas as _pd_shift
                            _df.index = _df.index + _pd_shift.offsets.BDay(int(_shift_bars))
                            _df.index.name = "timestamp"

                        _freq = detect_frequency(_df.index)
                        _n_raw = len(_df)
                        if _freq in ("weekly", "monthly"):
                            _df = _df.resample("B").ffill().dropna(subset=["close"])

                    # ── Résumé d'import ──────────────────────────────────────
                    _asset_class = _FRED_ROLES[_fred_role]
                    _fred_prov = "alfred" if _mode_key == "first" else "fred"
                    _fred_src_meta = {"provider": _fred_prov, "currency": _fred_currency_stored,
                                      "asset_class": _asset_class, "ticker": _ticker_val,
                                      "series_id": _series_id}
                    _existing_fred = _normalizer.load_parquet(_ticker_val, Path("DATASETS"))
                    if _existing_fred is not None:
                        # Fusion : existant en premier, nouveau en dernier → nouveau gagne (révisions)
                        _merged_fred = pd.concat([_existing_fred, _df])
                        _merged_fred = _merged_fred[~_merged_fred.index.duplicated(keep="last")]
                        _merged_fred = _merged_fred.sort_index()
                        _df = _merged_fred
                    _normalizer.save_parquet(_df, _ticker_val, _asset_class, Path("DATASETS"),
                                             source_meta=_fred_src_meta)
                    _cat.register(
                        ticker=_ticker_val,
                        name=_series_name,
                        asset_class=_asset_class,
                        currency=_fred_currency_stored,
                        provider="fred" if _mode_key == "latest" else "alfred",
                        df=_df,
                    )
                    _list_tickers.clear()

                    st.session_state["_fred_import_result"] = {
                        "ticker":      _ticker_val,
                        "series_id":   _series_id,
                        "name":        _series_name,
                        "role":        _fred_role,
                        "unit":        _fred_currency_stored,
                        "unit_auto":   _fred_currency == _UNIT_AUTO,
                        "unit_raw":    _sinfo.get("units", "?"),
                        "mode":        _mode,
                        "transform":   _transform_label,
                        "frequency":   _sinfo.get("frequency", _freq),
                        "n_raw":       _n_raw,
                        "n_stored":    len(_df),
                        "date_start":  str(_df.index.min().date()),
                        "date_end":    str(_df.index.max().date()),
                        "shift_bars":  int(_shift_bars),
                    }
                    st.rerun()

                except Exception as _e:
                    st.error(f"Import failed: {_e}")

        # ── Résumé d'import persistant ─────────────────────────────────────────
        if "_fred_import_result" in st.session_state:
            _r = st.session_state["_fred_import_result"]
            st.success(f"✓ **{_r['ticker']}** imported successfully")
            with st.expander("Import summary", expanded=True):
                _c1, _c2 = st.columns(2)
                with _c1:
                    st.markdown(f"**Series ID** : `{_r['series_id']}`")
                    st.markdown(f"**Name** : {_r['name']}")
                    st.markdown(f"**Ticker saved as** : `{_r['ticker']}`")
                    st.markdown(f"**Asset role** : {_r['role']}")
                    st.markdown(
                        f"**Unit** : {_r['unit']}"
                        + (f"  *(resolved from: {_r['unit_raw']})*" if _r["unit_auto"] else "")
                    )
                with _c2:
                    st.markdown(f"**Mode** : {_r['mode']}")
                    st.markdown(f"**Transformation** : {_r['transform']}")
                    _sb = _r.get("shift_bars", 0)
                    if _sb:
                        st.markdown(f"**Date shift** : +{_sb} business days applied")
                    st.markdown(f"**Source frequency** : {_r['frequency']}")
                    st.markdown(f"**Original bars** : {_r['n_raw']:,}")
                    st.markdown(f"**Daily bars stored** : {_r['n_stored']:,}")
                    st.markdown(f"**Date range** : {_r['date_start']} → {_r['date_end']}")

        with st.expander("How does ALFRED eliminate look-ahead bias?", expanded=False):
            st.markdown(
                """
**The problem with standard FRED dates**

FRED dates monthly series to the 1st of the reference month — e.g., January 2024 CPI
is dated `2024-01-01`. But in reality, that CPI figure was published on **February 13, 2024**.
If your strategy uses it on January 1st, you're using data that didn't exist yet.

**What ALFRED does**

ALFRED stores every revision of every data point with its `realtime_start` — the exact date
the value first became publicly available. When you import in **First publication** mode,
the index of the dataset becomes those real publication dates.

Your strategy running on February 1st, 2024 sees no CPI update. On February 13th, it sees
the January reading for the first time — exactly as it would have in real life.

**Latest revision mode**

Useful for research and analysis when you want the best available estimate of historical
reality, not the real-time experience. Not suitable for realistic backtesting.
                """
            )

    with tab6:
        st.subheader("Derived series")
        st.info(
            "Use this tab if you need a series that doesn't exist yet in your databank "
            "but can be **computed from two series you already have**. "
            "Common examples: a ratio between two volatility indexes (VIX3M / VIX), "
            "a percentage of total volume (up-volume / total-volume × 100), "
            "or any custom spread between two indicators. "
            "The result is saved as a new dataset and immediately available in the builder and backtest pages.",
            icon="ℹ️",
        )
        try:
            from databank.derived import DerivedSeriesManager
            dm = DerivedSeriesManager()
            derived = dm.list()
            if derived:
                import pandas as pd
                _der_rows = []
                for d in derived:
                    _der_rows.append({
                        "Name":        d.get("name", ""),
                        "Formula":     d.get("formula", ""),
                        "Components":  ", ".join(d.get("components", [])),
                        "Unit":        d.get("currency", ""),
                        "Description": d.get("description", ""),
                    })
                st.dataframe(pd.DataFrame(_der_rows), use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Cannot load derived series: {e}")

        st.subheader("Add a derived series")
        col_n, col_f, col_u, col_d, col_btn2 = st.columns([2, 3, 2, 3, 1])
        with col_n:
            d_name = st.text_input("Name", key="der_name").upper()
        with col_f:
            d_formula = st.text_input("Formula  (e.g. UVOL / (UVOL + DVOL))", key="der_formula")
        with col_u:
            d_unit = st.selectbox(
                "Unit",
                ["Other", "Index value", "% (rate / yield)", "USD"],
                key="der_unit",
            )
        with col_d:
            d_desc = st.text_input("Description", key="der_desc")
        with col_btn2:
            st.write("")
            st.write("")
            if st.button("➕  Add", key="der_add_btn"):
                if d_name and d_formula:
                    import subprocess
                    cmd = [sys.executable, "-m", "databank.updater", "derived", "add",
                           "--name", d_name, "--formula", d_formula,
                           "--currency", d_unit]
                    if d_desc:
                        cmd += ["--description", d_desc]
                    subprocess.run(cmd, capture_output=True)
                    st.success(f"{d_name} added.")
                    st.rerun()

        if st.button("🔄  Recompute all derived series", type="secondary"):
            import subprocess
            with st.spinner("Computing…"):
                r = subprocess.run(
                    [sys.executable, "-m", "databank.updater", "derived", "compute"],
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
            st.code(r.stdout + r.stderr)


# ===========================================================================
# PAGE: RESULTS
# ===========================================================================

elif page == "📊 Results":
    st.title("📊 Previous results")

    # ── Previous runs — interactive charts ───────────────────────────────────
    import json as _json
    import types as _types
    _run_files = sorted(
        (p for p in Path("logs").glob("*.json") if not p.name.endswith("_audit.json")),
        reverse=True,
    )

    if not _run_files:
        st.info("No results yet. Run a backtest first.")
    else:
        # Build selectbox labels from JSON metadata
        _run_options: dict[str, Path] = {}
        for _p in _run_files[:30]:
            try:
                with open(_p, encoding="utf-8") as _f:
                    _meta = _json.load(_f)
                _label = f"{_meta.get('title', _p.stem)}  —  {_meta.get('saved_at', '')[:10]}"
            except Exception:
                _label = _p.stem
            _run_options[_label] = _p

        _sel_col, _del_col = st.columns([5, 1])
        with _sel_col:
            _sel = st.selectbox("Select a run", list(_run_options.keys()), index=0, key="results_run_sel")
        with _del_col:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("🗑  Delete", key="results_del_btn", use_container_width=True):
                st.session_state["_results_del_pending"] = _sel

        # ── Confirmation ──────────────────────────────────────────────────────
        if st.session_state.get("_results_del_pending") == _sel:
            st.warning(f"Delete **{_sel}** ? This cannot be undone.")
            _dc1, _dc2 = st.columns([1, 1])
            with _dc1:
                if st.button("Yes, delete", key="results_del_confirm", type="primary"):
                    _run_options[_sel].unlink(missing_ok=True)
                    _audit = _run_options[_sel].with_name(
                        _run_options[_sel].stem + "_audit.json"
                    )
                    _audit.unlink(missing_ok=True)
                    _load_run_summary.clear()
                    st.session_state.pop("_results_del_pending", None)
                    st.session_state.pop("results_run_sel", None)
                    st.rerun()
            with _dc2:
                if st.button("Cancel", key="results_del_cancel"):
                    st.session_state.pop("_results_del_pending", None)
                    st.rerun()

        if _sel:
            try:
                with open(_run_options[_sel], encoding="utf-8") as _f:
                    _data = _json.load(_f)

                # Reconstruct equity curve
                import pandas as _pd_res
                _eq = _pd_res.Series(
                    _data["equity_curve"]["values"],
                    index=_pd_res.DatetimeIndex(_data["equity_curve"]["index"]),
                    name="equity",
                )

                # Reconstruct trades as lightweight namespace objects
                _trades = []
                for _td in _data.get("trades", []):
                    _t = _types.SimpleNamespace(**_td)
                    _t.entry_time = _pd_res.Timestamp(_td["entry_time"])
                    _t.exit_time  = _pd_res.Timestamp(_td["exit_time"])
                    _trades.append(_t)

                # ── Chart options ─────────────────────────────────────────────
                _bench_options = _list_tickers(tradeable_only=True) or _list_tickers()
                _roa, _rob, _roc = st.columns([3, 1, 2])
                with _roa:
                    _r_bench = st.selectbox(
                        "Benchmark", ["None"] + _bench_options, key="res_bench",
                    )
                with _rob:
                    _r_eq_ma = st.number_input(
                        "Equity MA", min_value=0, max_value=200, value=0,
                        step=5, key="res_eq_ma",
                        help="Rolling MA overlay on equity curve (0 = off)",
                    )
                with _roc:
                    if _trades:
                        _csv_rows = [
                            f"{t.entry_time},{t.exit_time},{t.symbol},"
                            f"{t.direction},{t.entry_price},{t.exit_price},"
                            f"{t.quantity},{t.pnl},{t.exit_reason}"
                            for t in _trades
                        ]
                        _csv_str = (
                            "entry_time,exit_time,symbol,direction,"
                            "entry_price,exit_price,quantity,pnl,exit_reason\n"
                            + "\n".join(_csv_rows)
                        )
                        st.markdown('<p style="margin:0 0 0.35rem 0;font-size:0.875rem;color:rgba(49,51,63,0.6)">Export</p>', unsafe_allow_html=True)
                        st.download_button(
                            "⬇  Download trades (CSV)",
                            data=_csv_str,
                            file_name=f"{_run_options[_sel].stem}_trades.csv",
                            mime="text/csv",
                            key="res_dl_trades",
                            use_container_width=True,
                        )

                _rcb1, _rcb2, _rcb3, _rcb4 = st.columns(4)
                with _rcb1:
                    _r_outperf = st.checkbox(
                        "Outperformance", value=True, key="res_outperf",
                        disabled=(_r_bench == "None"),
                    )
                with _rcb2:
                    _r_show_trades = st.checkbox("Trade markers", value=True, key="res_trades")
                with _rcb3:
                    _r_show_dd = st.checkbox("Drawdown", value=True, key="res_dd")
                with _rcb4:
                    _r_log = st.checkbox("Log scale", value=False, key="res_log")

                # ── Load benchmark ────────────────────────────────────────────
                _r_bench_series = None
                if _r_bench != "None":
                    _eq_start = str(_eq.index[0].date())
                    _eq_end   = str(_eq.index[-1].date())
                    with st.spinner(f"Loading {_r_bench}…"):
                        _r_bench_series = _load_benchmark(_r_bench, _eq_start, _eq_end)
                    if _r_bench_series is None:
                        st.warning(f"Could not load benchmark data for {_r_bench}.")

                _archived_fig = _build_plotly_chart(
                    equity_curve=_eq,
                    trades=_trades,
                    metrics=_data.get("metrics", {}),
                    title=_data.get("title", ""),
                    benchmark=_r_bench_series,
                    benchmark_label=_r_bench if _r_bench != "None" else "Benchmark",
                    show_trades=_r_show_trades,
                    show_drawdown=_r_show_dd,
                    show_outperformance=_r_outperf and _r_bench_series is not None,
                    show_equity_ma=int(_r_eq_ma),
                    log_scale=_r_log,
                    theme=st.session_state.get("app_theme", "light"),
                )
                if _archived_fig is not None:
                    st.plotly_chart(_archived_fig, use_container_width=True, key="archived_chart")
                else:
                    st.warning("Could not render chart.")

                # ── Performance statistics ────────────────────────────────────
                _rm = _data.get("metrics", {})
                # Always recompute exit-reason counts from stored trades so that
                # runs saved before the basket_stop_loss/basket_take_profit fix
                # are displayed correctly without having to re-run the backtest.
                _stored_trades = _data.get("trades", [])
                if _stored_trades:
                    _rm["n_stop_loss"]   = sum(1 for _t in _stored_trades if _t.get("exit_reason") in ("stop_loss",  "basket_stop_loss"))
                    _rm["n_take_profit"] = sum(1 for _t in _stored_trades if _t.get("exit_reason") in ("take_profit", "basket_take_profit"))
                    _rm["n_signal_exit"] = sum(1 for _t in _stored_trades if _t.get("exit_reason") not in ("stop_loss", "basket_stop_loss", "take_profit", "basket_take_profit"))
                if _rm:
                    st.markdown("---")

                    _th = st.session_state.get("app_theme", "light")
                    _pos_c = "#2E7D32" if _th == "light" else "#3FB950"
                    _neg_c = "#C62828" if _th == "light" else "#F85149"
                    _neu_c = "#1565C0" if _th == "light" else "#58A6FF"

                    def _mc(v, positive_good=True):
                        if v > 0 and positive_good: return _pos_c
                        if v < 0 and positive_good: return _neg_c
                        return _neu_c

                    _n_bars = len(_eq)
                    _capital = _rm.get("final_equity", 0) / (1 + _rm.get("total_return_pct", 0) / 100) if _rm.get("total_return_pct", 0) != -100 else 0

                    # Row 1 — Returns & drawdown
                    st.caption("**Performance**")
                    _m1, _m2, _m3, _m4, _m5, _m6 = st.columns(6)
                    _m1.metric("Final capital",        f"${_rm.get('final_equity', 0):,.0f}")
                    _m2.metric("Total return",         f"{_rm.get('total_return_pct', 0):+.2f}%")
                    _m3.metric("CAGR",                 f"{_rm.get('cagr_pct', 0):+.2f}%")
                    _m4.metric("Max drawdown",         f"{_rm.get('max_drawdown_pct', 0):.2f}%")
                    _m5.metric("Max DD duration",      f"{_rm.get('max_drawdown_duration_days', 0)} days")
                    _m6.metric("Bars processed",       f"{_n_bars:,}")

                    # Row 2 — Risk-adjusted ratios
                    st.caption("**Risk-adjusted ratios**")
                    _m7, _m8, _m9, _m10, _m11, _m12 = st.columns(6)
                    _sortino = _rm.get('sortino_ratio', 0)
                    _calmar  = _rm.get('calmar_ratio', 0)
                    _m7.metric("Sharpe ratio",         f"{_rm.get('sharpe_ratio', 0):.3f}")
                    _m8.metric("Sortino ratio",        f"{_sortino:.3f}" if _sortino != float('inf') else "∞")
                    _m9.metric("Calmar ratio",         f"{_calmar:.3f}"  if _calmar  != float('inf') else "∞")
                    _m10.metric("Profit factor",       f"{_rm.get('profit_factor', 0):.3f}" if _rm.get('profit_factor', 0) != float('inf') else "∞")
                    _m11.metric("Avg trade PnL",       f"${_rm.get('avg_trade_pnl', 0):+,.2f}")
                    _m12.metric("Total commissions",   f"${_rm.get('total_commission', 0):,.2f}")

                    # Row 3 — Trade breakdown
                    st.caption("**Trades**")
                    _m13, _m14, _m15, _m16, _m17, _m18 = st.columns(6)
                    _m13.metric("Total trades",        str(_rm.get('n_trades', 0)))
                    _m14.metric("Win rate",            f"{_rm.get('win_rate_pct', 0):.1f}%")
                    _m15.metric("Winners / Losers",    f"{_rm.get('n_winners', 0)} / {_rm.get('n_losers', 0)}")
                    _m16.metric("Avg win",             f"{_rm.get('avg_win_pct', 0):+.2f}%")
                    _m17.metric("Avg loss",            f"{_rm.get('avg_loss_pct', 0):+.2f}%")
                    _n_sig = _rm.get('n_signal_exit', 0) + _rm.get('n_stop_loss', 0) + _rm.get('n_take_profit', 0)
                    _m18.metric("Signal / SL / TP",
                                f"{_rm.get('n_signal_exit', 0)} / {_rm.get('n_stop_loss', 0)} / {_rm.get('n_take_profit', 0)}")

            except Exception as _load_err:
                st.error(f"Could not load result: {_load_err}")

        st.caption(f"{len(_run_files)} run(s) saved in `logs/`")
