"""
strategy_builder.py — Assistant de création de stratégie.

Génère un fichier .py dans strategies/ sans écrire une ligne de code.
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.chdir(Path(__file__).parent)
sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TECHNICAL_INDICATORS = [
    ("RSI",             "RSI (0-100)",                       14),
    ("SMA",             "Moyenne mobile simple",             20),
    ("EMA",             "Moyenne mobile exponentielle",      20),
    ("ATR",             "Average True Range",                14),
    ("STOCH_K",         "Stochastique %K (0-100)",           14),
    ("MOMENTUM",        "Momentum (close/close[n])",         10),
    ("ROC",             "Rate of Change (%)",                10),
    ("BOLLINGER_UPPER", "Bande de Bollinger superieure",     20),
    ("BOLLINGER_MID",   "Bande de Bollinger mediane",        20),
    ("BOLLINGER_LOWER", "Bande de Bollinger inferieure",     20),
    ("HIGHEST_HIGH",    "Plus haut sur n barres",            20),
    ("LOWEST_LOW",      "Plus bas sur n barres",             20),
    ("VWAP",            "Volume Weighted Average Price",     20),
]

OPERATORS = [
    ("<",             "est inferieur a"),
    (">",             "est superieur a"),
    ("<=",            "est inferieur ou egal a"),
    (">=",            "est superieur ou egal a"),
    ("crosses_above", "croise a la hausse"),
    ("crosses_below", "croise a la baisse"),
]

W = 60


# ---------------------------------------------------------------------------
# Helpers UI
# ---------------------------------------------------------------------------

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def header(title="NOUVELLE STRATEGIE"):
    print("=" * W)
    print(f"  {title}")
    print("=" * W)

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix} : ").strip()
    return val if val else default

def ask_float(prompt: str, default: float) -> float:
    val = ask(prompt, str(default))
    try:
        return float(val)
    except ValueError:
        return default

def pick(title: str, options: list[str], descriptions: list[str] = None) -> int:
    """Retourne l'index choisi (0-based), ou -1 pour retour/annuler."""
    if title:
        print(f"\n  {title}")
        print(f"  {'-' * (W - 2)}")
    for i, opt in enumerate(options, 1):
        desc = f"  -- {descriptions[i-1]}" if descriptions else ""
        print(f"    {i:>2}.  {opt}{desc}")
    print(f"     0.  Retour / Annuler")
    while True:
        raw = input("  > ").strip()
        if raw == "0":
            return -1
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print("  Choix invalide.")

def pause():
    input("\n  Appuyez sur Entree pour continuer...")


# ---------------------------------------------------------------------------
# Structure d'une condition
# ---------------------------------------------------------------------------

class Condition:
    """
    Une règle : LEFT OP RIGHT

    Types de côtés :
      "indicator"        — indicateur technique sur les barres de l'asset principal
      "series_indicator" — indicateur technique appliqué sur une série breadth
                           ex : SMA(5) sur ADVDEC.NY
      "series"           — valeur brute (close du dernier bar) d'une série breadth
      "bar"              — champ OHLCV de la barre courante (close, open, high, low)
      "value"            — constante numérique (côté droit uniquement)
    """

    def __init__(
        self,
        left_type: str,
        left_name: str,
        left_period: int,
        op: str,
        right_type: str,
        right_value: float = 0.0,
        right_name: str = "",
        right_period: int = 0,
        logic: str = "AND",
        left_series: str = "",   # pour series_indicator : la série sur laquelle appliquer l'indicateur
        right_series: str = "",  # idem côté droit
        lookback: int = 0,       # 0 = condition doit être vraie aujourd'hui
                                 # N > 0 = reste active N barres après la dernière fois vraie (latch)
        persistence: int = 0,    # N > 0 = doit être vraie N barres consécutives pour valider
    ):
        self.left_type    = left_type
        self.left_name    = left_name
        self.left_period  = left_period
        self.left_series  = left_series
        self.op           = op
        self.right_type   = right_type
        self.right_value  = right_value
        self.right_name   = right_name
        self.right_period = right_period
        self.right_series = right_series
        self.logic        = logic
        self.lookback     = lookback
        self.persistence  = persistence

    def human_readable(self) -> str:
        left  = self._side_label(self.left_type,  self.left_name,  self.left_period,
                                 self.left_series)
        right = self._side_label(self.right_type, self.right_name, self.right_period,
                                 self.right_series, self.right_value)
        op_label = {
            "<": "<", ">": ">", "<=": "<=", ">=": ">=",
            "crosses_above": "croise a la hausse",
            "crosses_below": "croise a la baisse",
        }.get(self.op, self.op)
        base = f"{left}  {op_label}  {right}"
        if self.lookback > 0:
            base += f"  [latch {self.lookback} bars]"
        elif self.persistence > 0:
            base += f"  [for {self.persistence} consecutive bars]"
        return base

    def _side_label(self, typ, name, period, series, value=None) -> str:
        if typ == "indicator":
            return f"{name}({period})"
        elif typ == "series_indicator":
            return f"{name}({period}) [sur {series}]"
        elif typ == "series":
            return name
        elif typ == "bar":
            return name
        else:  # value
            return str(value)


# ---------------------------------------------------------------------------
# Basket — groupe d'assets partageant les mêmes conditions d'entrée/sortie
# ---------------------------------------------------------------------------

@dataclass
class Basket:
    id:             str                      # "basket_1", "basket_2", ...
    assets:         list[str]                # ["NDX", "SPX"]
    weights:        dict[str, float]         # {"NDX": 0.60, "SPX": 0.40}  (must sum to 1.0)
    basket_size:    float                    # 0.20 = 20% of total capital
    basket_sl:      Optional[float]          # 0.03 = -3% basket P&L triggers close
    basket_tp:      Optional[float]          # 0.05 = +5% basket P&L triggers close
    entry:          list[Condition] = dc_field(default_factory=list)
    exit_:          list[Condition] = dc_field(default_factory=list)
    short_entry:    list[Condition] = dc_field(default_factory=list)
    cover_exit:     list[Condition] = dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Générateur de code
# ---------------------------------------------------------------------------

class CodeGenerator:

    def generate(
        self,
        name: str,
        class_name: str,
        symbol: str,
        position_size: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        entry: list[Condition],
        exit_: list[Condition],
        short_entry: Optional[list[Condition]] = None,
        cover_exit: Optional[list[Condition]] = None,
        description: str = "",
        execution_mode: str = "netting",
    ) -> str:
        """Backward-compatible single-asset generator. Delegates to generate_multi."""
        basket = Basket(
            id="basket_1",
            assets=[symbol],
            weights={symbol: 1.0},
            basket_size=position_size,
            basket_sl=stop_loss,
            basket_tp=take_profit,
            entry=entry or [],
            exit_=exit_ or [],
            short_entry=short_entry or [],
            cover_exit=cover_exit or [],
        )
        return self.generate_multi(
            name=name, class_name=class_name,
            baskets=[basket], description=description,
            execution_mode=execution_mode,
        )

    def _generate_legacy(
        self,
        name: str,
        class_name: str,
        symbol: str,
        position_size: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        entry: list[Condition],
        exit_: list[Condition],
        short_entry: Optional[list[Condition]] = None,
        cover_exit: Optional[list[Condition]] = None,
        description: str = "",
        execution_mode: str = "netting",
    ) -> str:
        """Original single-asset code generator (kept for reference)."""
        short_entry = short_entry or []
        cover_exit  = cover_exit  or []
        all_conds = entry + exit_ + short_entry + cover_exit
        needs_crossing = any(c.op in ("crosses_above", "crosses_below") for c in all_conds)
        extra = 2 if needs_crossing else 1

        lines = []

        # En-tête
        lines += [
            '"""',
            f'strategies/{name}.py',
            f'Strategie : {description or name}',
            f'Generee le {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            f'Asset : {symbol}',
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "from backtest.strategy.base import BaseStrategy",
            "from backtest.strategy.indicators import compute_indicator",
            "",
            "",
            f"class {class_name}(BaseStrategy):",
            "",
            f'    strategy_id    = "{name}"',
            f"    position_size  = {position_size}",
            f"    stop_loss      = {stop_loss}",
            f"    take_profit    = {take_profit}",
            f'    execution_mode = "{execution_mode}"',
            "",
            "    def on_bar(self, symbol: str, bar: pd.Series) -> None:",
        ]

        snap_items = []

        # --- Indicateurs sur l'asset principal ---
        main_inds = self._collect_main_indicators(all_conds)
        if main_inds:
            max_p   = max(p for _, p in main_inds)
            n_bars  = max_p + extra
            lines  += [
                f"        # Indicateurs sur {symbol}",
                f"        _bars = self._data.get_latest_n_bars(symbol, {n_bars})",
                f"        if len(_bars) < {n_bars}:",
                f"            return",
                "",
            ]
            seen = set()
            for ind, period in main_inds:
                var = self._var(ind, period)
                if var in seen:
                    continue
                seen.add(var)
                lines.append(f"        {var} = compute_indicator(\"{ind}\", _bars, {period})")
                if needs_crossing:
                    lines.append(
                        f"        {var}_prev = compute_indicator(\"{ind}\", _bars.iloc[:-1], {period})"
                    )
                snap_items.append(f'            "{ind}_{period}": round({var}, 4),')
            lines.append("")

        # --- Indicateurs sur séries breadth ---
        series_inds = self._collect_series_indicators(all_conds)
        # group by series so we do one get_latest_n_bars per series
        by_series: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for ind, period, series in series_inds:
            by_series[series].append((ind, period))

        if by_series:
            lines.append("        # Indicateurs sur series breadth")
            for series, ind_list in by_series.items():
                max_p  = max(p for _, p in ind_list)
                n      = max_p + extra
                safe_s = self._safe(series)
                lines += [
                    f'        _{safe_s}_bars = self._data.get_latest_n_bars("{series}", {n})',
                    f"        if _{safe_s}_bars is None or len(_{safe_s}_bars) < {n}:",
                    f"            return",
                ]
                seen2 = set()
                for ind, period in ind_list:
                    var = self._series_ind_var(ind, period, series)
                    if var in seen2:
                        continue
                    seen2.add(var)
                    lines.append(
                        f"        {var} = compute_indicator(\"{ind}\", _{safe_s}_bars, {period})"
                    )
                    if needs_crossing:
                        lines.append(
                            f"        {var}_prev = compute_indicator(\"{ind}\", _{safe_s}_bars.iloc[:-1], {period})"
                        )
                    snap_items.append(f'            "{ind}_{period}_{series}": round({var}, 4),')
            lines.append("")

        # --- Séries breadth brutes ---
        raw_series = self._collect_raw_series(all_conds)
        if raw_series:
            lines.append("        # Series breadth brutes")
            for s in raw_series:
                var = self._safe(s)
                lines += [
                    f'        _{var}_bar = self._data.get_latest_bar("{s}")',
                    f"        {var} = _{var}_bar[\"close\"] if _{var}_bar is not None else None",
                    f"        if {var} is None:",
                    f"            return  # {s} non disponible",
                ]
                snap_items.append(f'            "{s}": round({var}, 4),')
            lines.append("")

        # Audit snapshot
        if snap_items:
            lines += ["        # Audit snapshot", "        _snapshot = {"]
            lines += snap_items
            lines += ["        }", ""]

        snapshot_arg = "_snapshot" if snap_items else "{}"

        # --- Conditions ---
        if entry:
            lines.append("        # Long entry condition")
            lines += self._build_expr(entry, "_entree")
            lines.append("")

        if short_entry:
            lines.append("        # Short entry condition")
            lines += self._build_expr(short_entry, "_short_entree")
            lines.append("")

        if exit_:
            lines.append("        # Flat exit condition")
            lines += self._build_expr(exit_, "_sortie")
            lines.append("")

        if cover_exit:
            lines.append("        # Cover exit condition")
            lines += self._build_expr(cover_exit, "_couverture")
            lines.append("")

        # --- Signaux ---
        has_short_side = bool(short_entry or cover_exit)

        if has_short_side:
            # Position tracking (direction managed locally; SL/TP exits are
            # handled by the risk manager and are transparent to this logic)
            lines += [
                "        # Position direction tracking",
                "        if not hasattr(self, '_pos_dir'):",
                "            self._pos_dir = {}",
                "        _dir = self._pos_dir.get(symbol)",
                "",
            ]
            first = True
            def _kw():
                nonlocal first
                k = "if" if first else "elif"
                first = False
                return k

            if entry:
                lines += [
                    f"        {_kw()} _entree:",
                    f'            self._pos_dir[symbol] = "LONG"',
                    f'            self.signal(symbol, "LONG", {snapshot_arg})',
                ]
            if short_entry:
                lines += [
                    f"        {_kw()} _short_entree:",
                    f'            self._pos_dir[symbol] = "SHORT"',
                    f'            self.signal(symbol, "SHORT", {snapshot_arg})',
                ]
            if exit_:
                lines += [
                    f'        {_kw()} _sortie and _dir == "LONG":',
                    f'            self._pos_dir[symbol] = None',
                    f'            self.signal(symbol, "FLAT", {snapshot_arg})',
                ]
            if cover_exit:
                lines += [
                    f'        {_kw()} _couverture and _dir == "SHORT":',
                    f'            self._pos_dir[symbol] = None',
                    f'            self.signal(symbol, "COVER", {snapshot_arg})',
                ]

        else:
            # Simple LONG-only strategy (original logic, no position tracking)
            if entry and exit_:
                lines += [
                    "        if _entree:",
                    f'            self.signal(symbol, "LONG", {snapshot_arg})',
                    "        elif _sortie:",
                    f'            self.signal(symbol, "FLAT", {snapshot_arg})',
                ]
            elif entry:
                lines += [
                    "        if _entree:",
                    f'            self.signal(symbol, "LONG", {snapshot_arg})',
                ]
            elif exit_:
                lines += [
                    "        if _sortie:",
                    f'            self.signal(symbol, "FLAT", {snapshot_arg})',
                ]

        return "\n".join(lines) + "\n"

    # -----------------------------------------------------------------------
    # Multi-basket code generator
    # -----------------------------------------------------------------------

    def generate_multi(
        self,
        name: str,
        class_name: str,
        baskets: list[Basket],
        description: str = "",
        execution_mode: str = "netting",
    ) -> str:
        """Generate a strategy file supporting one or more baskets."""
        # Collect all symbols across all baskets
        symbols = sorted({a for b in baskets for a in b.assets})

        # Determine if any basket has crossing conditions (need extra bar)
        all_conds_global = [c for b in baskets for c in b.entry + b.exit_ + b.short_entry + b.cover_exit]
        needs_crossing = any(c.op in ("crosses_above", "crosses_below") for c in all_conds_global)
        extra = 2 if needs_crossing else 1

        lines = []

        # Header
        lines += [
            '"""',
            f'strategies/{name}.py',
            f'Strategie : {description or name}',
            f'Generee le {datetime.now().strftime("%Y-%m-%d %H:%M")}',
            f'Assets : {", ".join(symbols)}',
            '"""',
            "from __future__ import annotations",
            "import pandas as pd",
            "from backtest.strategy.base import BaseStrategy",
            "from backtest.strategy.indicators import compute_indicator",
            "",
            "",
            f"class {class_name}(BaseStrategy):",
            "",
            f'    strategy_id    = "{name}"',
            f"    symbols        = {symbols!r}",
            f'    execution_mode = "{execution_mode}"',
            "",
        ]

        # Per-basket class-level constants
        for i, b in enumerate(baskets, 1):
            # Normalize weights
            total_w = sum(b.weights.get(a, 1.0) for a in b.assets)
            if total_w <= 0:
                total_w = 1.0
            norm_weights = {a: b.weights.get(a, 1.0) / total_w for a in b.assets}
            # Pre-compute per-asset sizes = basket_size * weight
            sizes = {a: round(b.basket_size * norm_weights[a], 8) for a in b.assets}
            lines += [
                f"    _B{i}_ASSETS = {tuple(b.assets)!r}",
                f"    _B{i}_SIZES  = {sizes!r}",
                f"    _B{i}_SL     = {b.basket_sl!r}",
                f"    _B{i}_TP     = {b.basket_tp!r}",
                "",
            ]

        lines.append("    def on_bar(self, symbol: str, bar: pd.Series) -> None:")

        # ── Shared breadth/series indicators (all baskets, computed once) ──
        shared_series_inds: dict[tuple[str, int, str], None] = {}
        shared_raw_series: dict[str, None] = {}
        for b in baskets:
            all_conds_b = b.entry + b.exit_ + b.short_entry + b.cover_exit
            for ind, period, series in self._collect_series_indicators(all_conds_b):
                shared_series_inds[(ind, period, series)] = None
            for s in self._collect_raw_series(all_conds_b):
                shared_raw_series[s] = None

        # Shared series indicators
        if shared_series_inds:
            lines.append("        # \u2500\u2500 Shared indicators \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
            by_series: dict[str, list[tuple[str, int]]] = defaultdict(list)
            for (ind, period, series) in shared_series_inds:
                by_series[series].append((ind, period))
            for series, ind_list in by_series.items():
                max_p  = max(p for _, p in ind_list)
                n      = max_p + extra
                safe_s = self._safe(series)
                lines += [
                    f'        _{safe_s}_bars = self._data.get_latest_n_bars("{series}", {n})',
                    f"        if _{safe_s}_bars is None or len(_{safe_s}_bars) < {n}:",
                    f"            return",
                ]
                seen_si: set[str] = set()
                for ind, period in ind_list:
                    var = self._series_ind_var(ind, period, series)
                    if var in seen_si:
                        continue
                    seen_si.add(var)
                    lines.append(
                        f"        {var} = compute_indicator(\"{ind}\", _{safe_s}_bars, {period})"
                    )
                    if needs_crossing:
                        lines.append(
                            f"        {var}_prev = compute_indicator(\"{ind}\", _{safe_s}_bars.iloc[:-1], {period})"
                        )
            lines.append("")

        # Shared raw series
        if shared_raw_series:
            lines.append("        # Shared raw series breadth")
            for s in shared_raw_series:
                var = self._safe(s)
                lines += [
                    f'        _{var}_bar = self._data.get_latest_bar("{s}")',
                    f"        {var} = _{var}_bar[\"close\"] if _{var}_bar is not None else None",
                    f"        if {var} is None:",
                    f"            return  # {s} non disponible",
                ]
            lines.append("")

        # ── Per-basket dispatch ──
        # Always use `if` (never `elif`) so that symbols shared across baskets
        # are processed by every basket they belong to.
        for i, b in enumerate(baskets, 1):
            all_conds_b = b.entry + b.exit_ + b.short_entry + b.cover_exit

            # Compute basket header info
            total_w = sum(b.weights.get(a, 1.0) for a in b.assets)
            if total_w <= 0:
                total_w = 1.0
            norm_weights = {a: b.weights.get(a, 1.0) / total_w for a in b.assets}
            sizes = {a: round(b.basket_size * norm_weights[a], 8) for a in b.assets}
            size_pct  = round(sum(sizes.values()) * 100, 1)
            sl_str    = f"SL {b.basket_sl * 100:.1f}%" if b.basket_sl  is not None else "SL \u2014"
            tp_str    = f"TP {b.basket_tp * 100:.1f}%" if b.basket_tp  is not None else "TP \u2014"
            assets_str = ", ".join(b.assets)

            # Basket header separator
            _sep = "        # " + "\u2550" * 67
            lines += [
                _sep,
                f"        # BASKET {i}  \u00b7  {assets_str}  \u00b7  size {size_pct}%  \u00b7  {sl_str}  \u00b7  {tp_str}",
                _sep,
            ]

            lines.append(f"        if symbol in self._B{i}_ASSETS:")
            lines.append("")

            # Asset indicators
            main_inds = self._collect_main_indicators(all_conds_b)
            snap_items: list[str] = []
            if main_inds:
                max_p  = max(p for _, p in main_inds)
                n_bars = max_p + extra
                lines += [
                    f"            # Asset indicators",
                    f"            _bars = self._data.get_latest_n_bars(symbol, {n_bars})",
                    f"            if len(_bars) < {n_bars}:",
                    f"                return",
                ]
                seen_mi: set[str] = set()
                for iname, period in main_inds:
                    var = self._var(iname, period)
                    if var in seen_mi:
                        continue
                    seen_mi.add(var)
                    lines.append(f"            {var} = compute_indicator(\"{iname}\", _bars, {period})")
                    if needs_crossing:
                        lines.append(
                            f"            {var}_prev = compute_indicator(\"{iname}\", _bars.iloc[:-1], {period})"
                        )
                    snap_items.append(f'                "{iname}_{period}": round({var}, 4),')
                lines.append("")

            # Series snap items
            for (iname, period, series) in shared_series_inds:
                snap_items.append(
                    f'                "{iname}_{period}_{series}": round({self._series_ind_var(iname, period, series)}, 4),'
                )
            for s in shared_raw_series:
                snap_items.append(f'                "{s}": round({self._safe(s)}, 4),')

            # Snapshot
            snapshot_arg = "{}"
            if snap_items:
                lines += ["            # Snapshot", "            _snapshot = {"]
                lines += snap_items
                lines += ["            }", ""]
                snapshot_arg = "_snapshot"

            # Conditions — local vars (no basket prefix needed; in separate if/elif branch)
            _bi = "            "  # 12-space indent for basket block

            if b.entry:
                lines.append(f"{_bi}# \u2500\u2500\u2500 Entry \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                lines += self._build_expr(b.entry,       "_entry",
                                          basket_idx=i, cond_type="en", ind=_bi)
                lines.append("")
            if b.short_entry:
                lines.append(f"{_bi}# \u2500\u2500\u2500 Short entry \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                lines += self._build_expr(b.short_entry, "_short_entry",
                                          basket_idx=i, cond_type="sh", ind=_bi)
                lines.append("")
            if b.exit_:
                lines.append(f"{_bi}# \u2500\u2500\u2500 Exit  \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                lines += self._build_expr(b.exit_,       "_exit",
                                          basket_idx=i, cond_type="ex", ind=_bi)
                lines.append("")
            if b.cover_exit:
                lines.append(f"{_bi}# \u2500\u2500\u2500 Cover exit \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")
                lines += self._build_expr(b.cover_exit,  "_cover",
                                          basket_idx=i, cond_type="cv", ind=_bi)
                lines.append("")

            # Signals
            pd_var   = f"_pd_b{i}"
            bid      = b.id
            _ps_expr = f"self._B{i}_SIZES.get(symbol, self._B{i}_SIZES.get(list(self._B{i}_ASSETS)[0], 0.1))"
            _sl_expr = f"self._B{i}_SL"
            _tp_expr = f"self._B{i}_TP"

            prio_var = f"_prio_b{i}"
            prev_var = f"_prev_b{i}"
            has_both_long  = bool(b.entry and b.exit_)
            has_both_short = bool(b.short_entry and b.cover_exit)

            lines += [
                f"{_bi}# \u2500\u2500\u2500 Signals \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
                f"{_bi}if not hasattr(self, '{pd_var}'):",
                f"{_bi}    self.{pd_var} = {{}}",
                f"{_bi}_dir = self.{pd_var}.get(symbol)",
                "",
            ]

            # Priority-lock init block (only when both sides of a pair exist)
            if has_both_long or has_both_short:
                lines += [
                    f"{_bi}if not hasattr(self, '{prio_var}'):",
                    f"{_bi}    self.{prio_var} = {{}}",
                    f"{_bi}if not hasattr(self, '{prev_var}'):",
                    f"{_bi}    self.{prev_var} = {{}}",
                    "",
                ]

            # ── LONG pair priority lock ──────────────────────────────────────
            if has_both_long:
                lines += [
                    f"{_bi}# Priority lock — first condition to turn True wins.",
                    f"{_bi}# The other must wait until the first goes False.",
                    f"{_bi}_prio_l     = self.{prio_var}.get((symbol, 'l'))",
                    f"{_bi}_entry_rose = _entry and not self.{prev_var}.get((symbol, 'en'), False)",
                    f"{_bi}_exit_rose  = _exit  and not self.{prev_var}.get((symbol, 'ex'), False)",
                    f"{_bi}if _prio_l == 'en' and not _entry:",
                    f"{_bi}    _prio_l = 'ex' if _exit else None",
                    f"{_bi}elif _prio_l == 'ex' and not _exit:",
                    f"{_bi}    _prio_l = 'en' if _entry else None",
                    f"{_bi}if _entry_rose and _prio_l is None:",
                    f"{_bi}    _prio_l = 'en'",
                    f"{_bi}elif _exit_rose and _prio_l is None:",
                    f"{_bi}    _prio_l = 'ex'",
                    f"{_bi}self.{prio_var}[(symbol, 'l')] = _prio_l",
                    f"{_bi}self.{prev_var}[(symbol, 'en')] = bool(_entry)",
                    f"{_bi}self.{prev_var}[(symbol, 'ex')] = bool(_exit)",
                    "",
                    f"{_bi}if _prio_l == 'en':",
                    f'{_bi}    self.{pd_var}[symbol] = "LONG"',
                    f'{_bi}    self.signal(symbol, "LONG", {snapshot_arg},',
                    f'{_bi}                position_size={_ps_expr},',
                    f'{_bi}                basket_id="{bid}",',
                    f'{_bi}                basket_sl={_sl_expr}, basket_tp={_tp_expr})',
                    f'{_bi}elif _prio_l == \'ex\' and _dir == "LONG":',
                    f'{_bi}    self.{pd_var}[symbol] = None',
                    f'{_bi}    self.signal(symbol, "FLAT", {snapshot_arg}, basket_id="{bid}")',
                ]
            else:
                # Simple path — only one side defined, no conflict possible
                if b.entry:
                    lines += [
                        f"{_bi}if _entry:",
                        f'{_bi}    self.{pd_var}[symbol] = "LONG"',
                        f'{_bi}    self.signal(symbol, "LONG", {snapshot_arg},',
                        f'{_bi}                position_size={_ps_expr},',
                        f'{_bi}                basket_id="{bid}",',
                        f'{_bi}                basket_sl={_sl_expr}, basket_tp={_tp_expr})',
                    ]
                if b.exit_:
                    kw = "elif" if b.entry else "if"
                    lines += [
                        f'{_bi}{kw} _exit and _dir == "LONG":',
                        f'{_bi}    self.{pd_var}[symbol] = None',
                        f'{_bi}    self.signal(symbol, "FLAT", {snapshot_arg}, basket_id="{bid}")',
                    ]

            # ── SHORT pair priority lock ─────────────────────────────────────
            if has_both_short:
                lines += [
                    "",
                    f"{_bi}_prio_s      = self.{prio_var}.get((symbol, 's'))",
                    f"{_bi}_short_rose  = _short_entry and not self.{prev_var}.get((symbol, 'sh'), False)",
                    f"{_bi}_cover_rose  = _cover       and not self.{prev_var}.get((symbol, 'cv'), False)",
                    f"{_bi}if _prio_s == 'sh' and not _short_entry:",
                    f"{_bi}    _prio_s = 'cv' if _cover else None",
                    f"{_bi}elif _prio_s == 'cv' and not _cover:",
                    f"{_bi}    _prio_s = 'sh' if _short_entry else None",
                    f"{_bi}if _short_rose and _prio_s is None:",
                    f"{_bi}    _prio_s = 'sh'",
                    f"{_bi}elif _cover_rose and _prio_s is None:",
                    f"{_bi}    _prio_s = 'cv'",
                    f"{_bi}self.{prio_var}[(symbol, 's')] = _prio_s",
                    f"{_bi}self.{prev_var}[(symbol, 'sh')] = bool(_short_entry)",
                    f"{_bi}self.{prev_var}[(symbol, 'cv')] = bool(_cover)",
                    "",
                    f"{_bi}if _prio_s == 'sh':",
                    f'{_bi}    self.{pd_var}[symbol] = "SHORT"',
                    f'{_bi}    self.signal(symbol, "SHORT", {snapshot_arg},',
                    f'{_bi}                position_size={_ps_expr},',
                    f'{_bi}                basket_id="{bid}",',
                    f'{_bi}                basket_sl={_sl_expr}, basket_tp={_tp_expr})',
                    f'{_bi}elif _prio_s == \'cv\' and _dir == "SHORT":',
                    f'{_bi}    self.{pd_var}[symbol] = None',
                    f'{_bi}    self.signal(symbol, "COVER", {snapshot_arg}, basket_id="{bid}")',
                ]
            else:
                if b.short_entry:
                    kw = "elif" if (b.entry or b.exit_) else "if"
                    lines += [
                        f"{_bi}{kw} _short_entry:",
                        f'{_bi}    self.{pd_var}[symbol] = "SHORT"',
                        f'{_bi}    self.signal(symbol, "SHORT", {snapshot_arg},',
                        f'{_bi}                position_size={_ps_expr},',
                        f'{_bi}                basket_id="{bid}",',
                        f'{_bi}                basket_sl={_sl_expr}, basket_tp={_tp_expr})',
                    ]
                if b.cover_exit:
                    kw = "elif" if (b.entry or b.exit_ or b.short_entry) else "if"
                    lines += [
                        f'{_bi}{kw} _cover and _dir == "SHORT":',
                        f'{_bi}    self.{pd_var}[symbol] = None',
                        f'{_bi}    self.signal(symbol, "COVER", {snapshot_arg}, basket_id="{bid}")',
                    ]

            lines.append("")

        return "\n".join(lines) + "\n"

    # -----------------------------------------------------------------------
    # Collecte des dépendances
    # -----------------------------------------------------------------------

    def _collect_main_indicators(self, conds: list[Condition]) -> list[tuple[str, int]]:
        result, seen = [], set()
        for c in conds:
            for typ, name, period in [
                (c.left_type,  c.left_name,  c.left_period),
                (c.right_type, c.right_name, c.right_period),
            ]:
                if typ == "indicator":
                    k = (name, period)
                    if k not in seen:
                        result.append(k)
                        seen.add(k)
        return result

    def _collect_series_indicators(self, conds: list[Condition]) -> list[tuple[str, int, str]]:
        result, seen = [], set()
        for c in conds:
            for typ, name, period, series in [
                (c.left_type,  c.left_name,  c.left_period,  c.left_series),
                (c.right_type, c.right_name, c.right_period, c.right_series),
            ]:
                if typ == "series_indicator":
                    k = (name, period, series)
                    if k not in seen:
                        result.append(k)
                        seen.add(k)
        return result

    def _collect_raw_series(self, conds: list[Condition]) -> list[str]:
        result, seen = [], set()
        for c in conds:
            for typ, name in [(c.left_type, c.left_name), (c.right_type, c.right_name)]:
                if typ == "series" and name not in seen:
                    result.append(name)
                    seen.add(name)
        return result

    # -----------------------------------------------------------------------
    # Nommage des variables
    # -----------------------------------------------------------------------

    def _safe(self, name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]", "_", name).lower()

    def _var(self, name: str, period: int) -> str:
        return f"_{name.lower()}_{period}"

    def _series_ind_var(self, ind: str, period: int, series: str) -> str:
        return f"_{ind.lower()}_{period}_{self._safe(series)}"

    # -----------------------------------------------------------------------
    # Construction des expressions
    # -----------------------------------------------------------------------

    def _side_expr(self, typ, name, period, series, value) -> tuple[str, str]:
        """Retourne (var_now, var_prev)."""
        if typ == "indicator":
            v = self._var(name, period)
            return v, v + "_prev"
        elif typ == "series_indicator":
            v = self._series_ind_var(name, period, series)
            return v, v + "_prev"
        elif typ == "series":
            v = self._safe(name)
            return v, v          # pas de _prev pour une série brute
        elif typ == "bar":
            v = f'bar["{name}"]'
            return v, v
        else:                    # value
            s = str(value)
            return s, s

    def _build_expr(self, conds: list[Condition], out_var: str,
                    basket_idx: int = 0, cond_type: str = "",
                    ind: str = "        ") -> list[str]:
        """Build expression lines for a list of conditions.

        Parameters
        ----------
        conds       : list of Condition objects
        out_var     : final boolean variable name, e.g. "_entry", "_exit"
        basket_idx  : basket number used in instance attribute names
        cond_type   : "en", "ex", "sh", "cv" -- used in instance attribute names
        ind         : base indentation string
        """
        lines = []

        has_state = any(
            getattr(c, "lookback", 0) > 0 or getattr(c, "persistence", 0) > 0
            for c in conds
        )

        if not has_state:
            # Fast path: single compound expression, no intermediate vars needed
            lines.append(f"{ind}{out_var} = (")
            for i, c in enumerate(conds):
                l_now, l_prev = self._side_expr(
                    c.left_type,  c.left_name,  c.left_period,  c.left_series,  None)
                r_now, r_prev = self._side_expr(
                    c.right_type, c.right_name, c.right_period, c.right_series, c.right_value)
                if c.op == "crosses_above":
                    expr = f"{l_now} >= {r_now} and {l_prev} < {r_prev}"
                elif c.op == "crosses_below":
                    expr = f"{l_now} <= {r_now} and {l_prev} > {r_prev}"
                else:
                    expr = f"{l_now} {c.op} {r_now}"
                prefix = f"{ind}    " if i == 0 else f"{ind}    {c.logic.lower()} "
                lines.append(f"{prefix}({expr})")
            lines.append(f"{ind})")
            return lines

        # Latch/persist path: emit _raw_N, state mechanics, _eff_N, then combine
        for i, c in enumerate(conds):
            lb = getattr(c, "lookback", 0)
            ps = getattr(c, "persistence", 0)
            raw_var = f"_raw_{i}"
            l_now, l_prev = self._side_expr(
                c.left_type,  c.left_name,  c.left_period,  c.left_series,  None)
            r_now, r_prev = self._side_expr(
                c.right_type, c.right_name, c.right_period, c.right_series, c.right_value)
            if c.op == "crosses_above":
                expr = f"{l_now} >= {r_now} and {l_prev} < {r_prev}"
            elif c.op == "crosses_below":
                expr = f"{l_now} <= {r_now} and {l_prev} > {r_prev}"
            else:
                expr = f"{l_now} {c.op} {r_now}"

            # Always emit a human-readable comment so the Review parser can
            # display every condition, even those without persistence/latch.
            lines.append(f"{ind}# {c.human_readable()}")
            lines.append(f"{ind}{raw_var} = ({expr})")

            if ps > 0 and lb > 0:
                # Persistence then latch: must be true ps consecutive bars,
                # then stays active lb bars even after condition turns false.
                pattr    = f"_persist_b{basket_idx}_{cond_type}_{i}"
                lattr    = f"_latch_b{basket_idx}_{cond_type}_{i}"
                trig_var = f"_trig_{i}"
                lines += [
                    f"{ind}if not hasattr(self, '{pattr}'):",
                    f"{ind}    self.{pattr} = {{}}",
                    f"{ind}if {raw_var}:",
                    f"{ind}    self.{pattr}[symbol] = self.{pattr}.get(symbol, 0) + 1",
                    f"{ind}else:",
                    f"{ind}    self.{pattr}[symbol] = 0",
                    f"{ind}{trig_var} = self.{pattr}.get(symbol, 0) >= {ps}",
                    f"{ind}if not hasattr(self, '{lattr}'):",
                    f"{ind}    self.{lattr} = {{}}",
                    f"{ind}if {trig_var}:",
                    f"{ind}    self.{lattr}[symbol] = {lb}",
                    f"{ind}elif symbol in self.{lattr}:",
                    f"{ind}    self.{lattr}[symbol] -= 1",
                    f"{ind}    if self.{lattr}[symbol] <= 0:",
                    f"{ind}        del self.{lattr}[symbol]",
                    f"{ind}_eff_{i} = symbol in self.{lattr}",
                ]
            elif lb > 0:
                # Latch only: stays active lb bars after last time condition was true
                lattr = f"_latch_b{basket_idx}_{cond_type}_{i}"
                lines += [
                    f"{ind}if not hasattr(self, '{lattr}'):",
                    f"{ind}    self.{lattr} = {{}}",
                    f"{ind}if {raw_var}:",
                    f"{ind}    self.{lattr}[symbol] = {lb}",
                    f"{ind}elif symbol in self.{lattr}:",
                    f"{ind}    self.{lattr}[symbol] -= 1",
                    f"{ind}    if self.{lattr}[symbol] <= 0:",
                    f"{ind}        del self.{lattr}[symbol]",
                    f"{ind}_eff_{i} = symbol in self.{lattr}",
                ]
            elif ps > 0:
                # Persistence only: must be true ps consecutive bars
                pattr = f"_persist_b{basket_idx}_{cond_type}_{i}"
                lines += [
                    f"{ind}if not hasattr(self, '{pattr}'):",
                    f"{ind}    self.{pattr} = {{}}",
                    f"{ind}if {raw_var}:",
                    f"{ind}    self.{pattr}[symbol] = self.{pattr}.get(symbol, 0) + 1",
                    f"{ind}else:",
                    f"{ind}    self.{pattr}[symbol] = 0",
                    f"{ind}_eff_{i} = self.{pattr}.get(symbol, 0) >= {ps}",
                ]
            else:
                lines.append(f"{ind}_eff_{i} = {raw_var}")

        # Combine effective conditions into final variable
        lines.append(f"{ind}{out_var} = (")
        for i, c in enumerate(conds):
            prefix = f"{ind}    " if i == 0 else f"{ind}    {c.logic.lower()} "
            lines.append(f"{prefix}(_eff_{i})")
        lines.append(f"{ind})")
        return lines


# ---------------------------------------------------------------------------
# Wizard interactif
# ---------------------------------------------------------------------------

class StrategyWizard:

    def run(self):
        clear()
        header("NOUVELLE STRATEGIE -- ASSISTANT")
        print()
        print("  Cet assistant cree un fichier .py dans strategies/")
        print("  Naviguez avec les chiffres, Entree pour valider.\n")

        # 1. Nom
        name = ask("Nom de la strategie (ex: ma_strategie_rsi)").strip()
        if not name:
            return
        name        = re.sub(r"[^a-z0-9_]", "_", name.lower())
        class_name  = "".join(w.capitalize() for w in name.split("_"))
        description = ask("Description courte", name)

        save_path = Path("strategies") / f"{name}.py"
        if save_path.exists():
            ow = ask(f"'{name}.py' existe deja. Ecraser ? (o/N)", "N").lower()
            if ow not in ("o", "oui", "y", "yes"):
                print("  Annule.")
                pause()
                return

        # 2. Asset à trader
        tradeable  = self._get_tradeable()
        all_tickers = self._get_tickers()

        clear()
        header("ASSET A TRADER")
        print()
        if tradeable:
            print("  Assets classifies comme index / equity / fx / crypto :")
            options = tradeable + ["[Voir tous les assets]"]
        else:
            print("  Aucun asset classe comme index/equity — liste complete :")
            options = all_tickers

        idx = pick("Selectionnez l'asset :", options)
        if idx == -1:
            return
        if options[idx] == "[Voir tous les assets]":
            idx2 = pick("Tous les assets :", all_tickers)
            if idx2 == -1:
                return
            symbol = all_tickers[idx2]
        else:
            symbol = options[idx]

        # 3. Risque
        clear()
        header("PARAMETRES DE RISQUE")
        print()
        position_size = ask_float("Position size  (ex: 0.10 = 10% du capital)", 0.10)
        sl_str  = ask("Stop loss      (ex: 0.02 = -2%, vide = aucun)", "")
        tp_str  = ask("Take profit    (ex: 0.05 = +5%, vide = aucun)", "")
        _none_words = {"", "vide", "aucun", "none", "no", "n", "-", "0"}
        stop_loss   = float(sl_str) if sl_str.lower() not in _none_words else None
        take_profit = float(tp_str) if tp_str.lower() not in _none_words else None

        # 4. Conditions d'entrée
        clear()
        header("CONDITIONS D'ENTREE")
        print()
        print("  Definissez les conditions pour ENTRER en position (LONG).\n")
        entry_conds = self._build_conditions("entree")
        if entry_conds is None:
            return

        # 5. Conditions de sortie
        clear()
        header("CONDITIONS DE SORTIE")
        print()
        print("  Definissez les conditions pour SORTIR de position (FLAT).")
        print("  (Stop loss / take profit sont geres automatiquement.)\n")
        exit_conds = self._build_conditions("sortie")
        if exit_conds is None:
            return

        # 6. Génération et aperçu
        gen  = CodeGenerator()
        code = gen.generate(
            name=name, class_name=class_name, symbol=symbol,
            position_size=position_size, stop_loss=stop_loss, take_profit=take_profit,
            entry=entry_conds, exit_=exit_conds, description=description,
        )

        clear()
        header("APERCU DU CODE GENERE")
        print()
        print(code)
        print("-" * W)

        print(f"\n  Asset         : {symbol}")
        print(f"  Position size : {position_size*100:.0f}%")
        print(f"  Stop loss     : {stop_loss*100:.1f}%" if stop_loss else "  Stop loss     : aucun")
        print(f"  Take profit   : {take_profit*100:.1f}%" if take_profit else "  Take profit   : aucun")
        if entry_conds:
            print(f"\n  Conditions d'entree ({len(entry_conds)}) :")
            for i, c in enumerate(entry_conds):
                prefix = "  SI   " if i == 0 else f"  {c.logic:<4} "
                print(f"  {prefix} {c.human_readable()}")
        if exit_conds:
            print(f"\n  Conditions de sortie ({len(exit_conds)}) :")
            for i, c in enumerate(exit_conds):
                prefix = "  SI   " if i == 0 else f"  {c.logic:<4} "
                print(f"  {prefix} {c.human_readable()}")

        print()
        confirm = ask("Sauvegarder cette strategie ? (O/n)", "O").lower()
        if confirm in ("n", "non", "no"):
            print("  Annule.")
            pause()
            return

        save_path.write_text(code, encoding="utf-8")
        print(f"\n  Strategie sauvegardee : {save_path}")
        print(f"  Elle apparaitra dans le menu 'Lancer un backtest'.")
        pause()

    # -----------------------------------------------------------------------
    # Construction des conditions
    # -----------------------------------------------------------------------

    def _build_conditions(self, label: str) -> Optional[list[Condition]]:
        conditions: list[Condition] = []

        while True:
            clear()
            header(f"CONDITIONS DE {label.upper()}")
            print()

            if conditions:
                print(f"  Conditions actuelles ({len(conditions)}) :")
                for i, c in enumerate(conditions):
                    prefix = "  SI   " if i == 0 else f"  {c.logic:<4} "
                    print(f"  {prefix} {c.human_readable()}")
                print()

            options = [
                "Indicateur technique sur l'asset           (RSI, SMA, ATR...)",
                "Indicateur technique sur une serie breadth  (SMA sur ADVDEC...)",
                "Valeur brute d'une serie breadth            (VIX, UVOL...)",
                "Valeur de barre                             (close, open, high, low)",
            ]
            if conditions:
                options.append("Terminer -- garder ces conditions")

            if not conditions:
                print("  Que voulez-vous utiliser comme condition ?")
            else:
                print("  Ajouter une condition ou terminer ?")

            idx = pick("", options)
            if idx == -1:
                # Retour/annuler : si sortie sans conditions = OK (stop/TP suffisent)
                if not conditions and label == "sortie":
                    return []
                return None  # annuler le wizard

            choice = options[idx]

            if "Terminer" in choice:
                return conditions

            logic = "AND"
            if conditions:
                log_idx = pick("Combiner avec la condition precedente :", ["ET (AND)", "OU (OR)"])
                if log_idx == -1:
                    continue
                logic = "AND" if log_idx == 0 else "OR"

            if "sur l'asset" in choice:
                cond = self._add_main_indicator_condition(logic)
            elif "sur une serie breadth" in choice:
                cond = self._add_series_indicator_condition(logic)
            elif "brute" in choice:
                cond = self._add_raw_series_condition(logic)
            else:
                cond = self._add_bar_condition(logic)

            if cond is not None:
                conditions.append(cond)

            if not conditions:
                skip = ask("Terminer sans condition ? (o/N)", "N").lower()
                if skip in ("o", "oui", "y", "yes"):
                    return []

        return conditions

    # -----------------------------------------------------------------------
    # Constructeurs de conditions individuelles
    # -----------------------------------------------------------------------

    def _add_main_indicator_condition(self, logic: str) -> Optional[Condition]:
        """Indicateur sur les barres de l'asset principal."""
        clear()
        header("INDICATEUR SUR L'ASSET")
        print()

        ind_name, period = self._pick_indicator()
        if ind_name is None:
            return None

        op = self._pick_op()
        if op is None:
            return None

        right_options = [
            "Valeur fixe                                 (ex: 30, 70, 200...)",
            "Autre indicateur technique sur l'asset",
            "Indicateur technique sur une serie breadth  (SMA sur VIX...)",
            "Valeur brute d'une serie breadth",
        ]
        r_idx = pick("Comparer avec :", right_options)
        if r_idx == -1:
            return None

        if r_idx == 0:
            val = ask_float("Valeur seuil", 0.0)
            return Condition("indicator", ind_name, period, op, "value",
                             right_value=val, logic=logic)
        elif r_idx == 1:
            rn, rp = self._pick_indicator("Quel indicateur (cote droit) ?")
            if rn is None:
                return None
            return Condition("indicator", ind_name, period, op, "indicator",
                             right_name=rn, right_period=rp, logic=logic)
        elif r_idx == 2:
            return self._pick_right_series_indicator(
                "indicator", ind_name, period, op, logic
            )
        else:
            s = self._pick_series("Serie breadth :")
            if s is None:
                return None
            return Condition("indicator", ind_name, period, op, "series",
                             right_name=s, logic=logic)

    def _add_series_indicator_condition(self, logic: str) -> Optional[Condition]:
        """Indicateur technique appliqué sur une série breadth."""
        clear()
        header("INDICATEUR SUR SERIE BREADTH")
        print()
        print("  Exemple : SMA(5) sur ADVDEC.NY  >  0")
        print("  Exemple : SMA(5) sur ADVDEC.NY  croise a la hausse  SMA(20) sur ADVDEC.NY\n")

        # Série gauche
        s_left = self._pick_series("Serie breadth (cote gauche) :")
        if s_left is None:
            return None

        # Indicateur à appliquer sur cette série
        ind_name, period = self._pick_indicator(f"Indicateur a appliquer sur {s_left} :")
        if ind_name is None:
            return None

        op = self._pick_op()
        if op is None:
            return None

        # Côté droit
        right_options = [
            f"Valeur fixe                                 (ex: 0, 500, -1000...)",
            f"Meme indicateur / autre periode sur {s_left}",
            f"Autre indicateur sur {s_left}",
            f"Indicateur sur une autre serie breadth",
            f"Valeur brute d'une serie breadth",
        ]
        r_idx = pick("Comparer avec :", right_options)
        if r_idx == -1:
            return None

        if r_idx == 0:
            val = ask_float("Valeur seuil", 0.0)
            return Condition("series_indicator", ind_name, period, op, "value",
                             right_value=val, left_series=s_left, logic=logic)

        elif r_idx in (1, 2):
            rn, rp = self._pick_indicator(f"Indicateur (cote droit) sur {s_left} :")
            if rn is None:
                return None
            return Condition("series_indicator", ind_name, period, op, "series_indicator",
                             right_name=rn, right_period=rp,
                             left_series=s_left, right_series=s_left, logic=logic)

        elif r_idx == 3:
            s_right = self._pick_series("Serie breadth (cote droit) :")
            if s_right is None:
                return None
            rn, rp = self._pick_indicator(f"Indicateur sur {s_right} :")
            if rn is None:
                return None
            return Condition("series_indicator", ind_name, period, op, "series_indicator",
                             right_name=rn, right_period=rp,
                             left_series=s_left, right_series=s_right, logic=logic)

        else:  # valeur brute
            s_right = self._pick_series("Serie breadth (cote droit) :")
            if s_right is None:
                return None
            return Condition("series_indicator", ind_name, period, op, "series",
                             right_name=s_right, left_series=s_left, logic=logic)

    def _pick_right_series_indicator(
        self, left_type, left_name, left_period, op, logic
    ) -> Optional[Condition]:
        """Sélecteur côté droit = indicateur appliqué sur une série breadth."""
        s = self._pick_series("Serie breadth (cote droit) :")
        if s is None:
            return None
        rn, rp = self._pick_indicator(f"Indicateur sur {s} :")
        if rn is None:
            return None
        return Condition(left_type, left_name, left_period, op, "series_indicator",
                         right_name=rn, right_period=rp, right_series=s, logic=logic)

    def _add_raw_series_condition(self, logic: str) -> Optional[Condition]:
        """Valeur brute (close) d'une série breadth."""
        clear()
        header("SERIE BREADTH BRUTE")
        print()

        s_left = self._pick_series("Serie :")
        if s_left is None:
            return None

        op = self._pick_op()
        if op is None:
            return None

        right_options = [
            "Valeur fixe",
            "Autre serie breadth brute",
        ]
        r_idx = pick("Comparer avec :", right_options)
        if r_idx == -1:
            return None

        if r_idx == 0:
            val = ask_float("Valeur seuil", 0.0)
            return Condition("series", s_left, 0, op, "value",
                             right_value=val, logic=logic)
        else:
            s_right = self._pick_series("Serie (cote droit) :")
            if s_right is None:
                return None
            return Condition("series", s_left, 0, op, "series",
                             right_name=s_right, logic=logic)

    def _add_bar_condition(self, logic: str) -> Optional[Condition]:
        """Champ OHLCV de la barre courante."""
        clear()
        header("VALEUR DE BARRE")
        print()

        bar_fields = ["close", "open", "high", "low", "volume"]
        idx = pick("Champ :", bar_fields)
        if idx == -1:
            return None
        field = bar_fields[idx]

        # Pas de crossing sur champ de barre simple
        op_names  = [o[0] for o in OPERATORS[:4]]
        op_labels = [o[1] for o in OPERATORS[:4]]
        op_idx = pick("Operateur :", op_names, op_labels)
        if op_idx == -1:
            return None
        op = op_names[op_idx]

        val = ask_float("Valeur seuil", 0.0)
        return Condition("bar", field, 0, op, "value", right_value=val, logic=logic)

    # -----------------------------------------------------------------------
    # Petits sélecteurs réutilisables
    # -----------------------------------------------------------------------

    def _pick_indicator(self, title: str = "Indicateur :") -> tuple[Optional[str], int]:
        names  = [t[0] for t in TECHNICAL_INDICATORS]
        labels = [f"{t[1]}  (defaut: {t[2]})" for t in TECHNICAL_INDICATORS]
        idx = pick(title, names, labels)
        if idx == -1:
            return None, 0
        ind_name, _, default_period = TECHNICAL_INDICATORS[idx]
        period = int(ask("Periode", str(default_period)))
        return ind_name, period

    def _pick_op(self, title: str = "Operateur :") -> Optional[str]:
        op_names  = [o[0] for o in OPERATORS]
        op_labels = [o[1] for o in OPERATORS]
        op_idx = pick(title, op_names, op_labels)
        if op_idx == -1:
            return None
        return op_names[op_idx]

    def _pick_series(self, title: str = "Serie breadth :") -> Optional[str]:
        series = self._get_indicator_series()
        if not series:
            print("  Aucune serie breadth disponible dans la databank.")
            pause()
            return None
        idx = pick(title, series)
        if idx == -1:
            return None
        return series[idx]

    # -----------------------------------------------------------------------
    # Données
    # -----------------------------------------------------------------------

    def _get_tickers(self) -> list[str]:
        try:
            from databank.catalog import list_assets
            return sorted(e["ticker"] for e in list_assets())
        except Exception:
            return []

    def _get_tradeable(self) -> list[str]:
        try:
            from databank.catalog import list_assets
            tradeable = {"index", "equity", "fx", "crypto"}
            return sorted(e["ticker"] for e in list_assets() if e.get("class") in tradeable)
        except Exception:
            return []

    def _get_indicator_series(self) -> list[str]:
        try:
            from databank.catalog import list_assets
            return sorted(e["ticker"] for e in list_assets() if e.get("class") == "indicator")
        except Exception:
            return []


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    StrategyWizard().run()
