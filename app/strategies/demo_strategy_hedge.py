"""
strategies/demo_strategy_hedge.py
Strategie : demo_strategy_hedge
Generee le 2026-03-23 21:57
Assets : AAPL, GC=F, ^NDX, ^GSPC, MSFT, CL=F
"""
# __builder__: {"name": "demo_strategy_hedge", "desc": "demo_strategy_hedge", "exec_mode": "hedge", "baskets": [{"id": "basket_1", "assets": ["AAPL", "MSFT", "^NDX", "^GSPC"], "weights": {"AAPL": 100.0, "MSFT": 50.0, "^NDX": 33.3, "^GSPC": 25.0}, "basket_size": 80.0, "basket_sl": 2.0, "basket_tp": 5.0, "use_custom_size": true, "use_sl": false, "use_tp": false, "entry_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "SMA", "left_period": 5, "left_series": "ADVDEC.NY", "op": ">", "right_type": "series_indicator", "right_name": "SMA", "right_period": 20, "right_series": "ADVDEC.NY", "right_value": 0.0, "lookback": 0, "persistence": 3, "human": "SMA(5) on ADVDEC.NY  >  SMA(20) on ADVDEC.NY  [≥3 consecutive bars]"}], "exit_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "^NDX", "op": "<", "right_type": "series_indicator", "right_name": "EMA", "right_period": 20, "right_series": "^NDX", "right_value": 0.0, "lookback": 0, "persistence": 3, "human": "RAW(1) on ^NDX  <  EMA(20) on ^NDX  [≥3 consecutive bars]"}], "short_entry_conds": [], "cover_exit_conds": []}, {"id": "basket_2", "assets": ["GC=F", "CL=F"], "weights": {"GC=F": 100.0, "CL=F": 50.0}, "basket_size": 60.0, "basket_sl": 2.0, "basket_tp": 5.0, "use_custom_size": true, "use_sl": false, "use_tp": false, "entry_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "CPI_YOY_PRELIM", "op": ">", "right_type": "series_indicator", "right_name": "SMA", "right_period": 4, "right_series": "CPI_YOY_PRELIM", "right_value": 0.0, "lookback": 0, "persistence": 0, "human": "RAW(1) on CPI_YOY_PRELIM  >  SMA(4) on CPI_YOY_PRELIM"}], "exit_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "CPI_YOY_PRELIM", "op": "<", "right_type": "series_indicator", "right_name": "SMA", "right_period": 4, "right_series": "CPI_YOY_PRELIM", "right_value": 0.0, "lookback": 0, "persistence": 0, "human": "RAW(1) on CPI_YOY_PRELIM  <  SMA(4) on CPI_YOY_PRELIM"}], "short_entry_conds": [], "cover_exit_conds": []}, {"id": "basket_3", "assets": ["^GSPC", "^NDX"], "weights": {"^GSPC": 100.0, "^NDX": 50.0}, "basket_size": 20.0, "basket_sl": 4.0, "basket_tp": 12.0, "use_custom_size": true, "use_sl": true, "use_tp": true, "entry_conds": [], "exit_conds": [], "short_entry_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "VIX3M_VIX", "op": "<", "right_type": "value", "right_name": "", "right_period": 0, "right_series": "", "right_value": 1.08, "lookback": 3, "persistence": 5, "human": "RAW(1) on VIX3M_VIX  <  1.08  [≥5 consecutive bars]  [latch 3 bars]"}, {"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "VIX3M_VIX", "op": "<", "right_type": "series_indicator", "right_name": "EMA", "right_period": 20, "right_series": "VIX3M_VIX", "right_value": 0.0, "lookback": 2, "persistence": 0, "human": "RAW(1) on VIX3M_VIX  <  EMA(20) on VIX3M_VIX  [latch 2 bars]"}], "cover_exit_conds": [{"logic": "AND", "left_type": "series_indicator", "left_name": "RAW", "left_period": 1, "left_series": "VIX3M_VIX", "op": "<", "right_type": "series_indicator", "right_name": "BOLLINGER_LOWER", "right_period": 20, "right_series": "VIX3M_VIX", "right_value": 0.0, "lookback": 0, "persistence": 0, "human": "RAW(1) on VIX3M_VIX  <  BOLLINGER_LOWER(20) on VIX3M_VIX"}]}]}
from __future__ import annotations
import pandas as pd
from backtest.strategy.base import BaseStrategy
from backtest.strategy.indicators import compute_indicator


class DemoStrategyHedge(BaseStrategy):

    strategy_id    = "demo_strategy_hedge"
    symbols        = ['AAPL', 'GC=F', '^NDX', '^GSPC', 'MSFT', 'CL=F']
    execution_mode = "hedge"

    _B1_ASSETS = ('AAPL', 'MSFT', '^NDX', '^GSPC')
    _B1_SIZES  = {'AAPL': 0.38406145, 'MSFT': 0.19203072, '^NDX': 0.12789246, '^GSPC': 0.09601536}
    _B1_SL     = None
    _B1_TP     = None

    _B2_ASSETS = ('GC=F', 'CL=F')
    _B2_SIZES  = {'GC=F': 0.4, 'CL=F': 0.2}
    _B2_SL     = None
    _B2_TP     = None

    _B3_ASSETS = ('^GSPC', '^NDX')
    _B3_SIZES  = {'^GSPC': 0.13333333, '^NDX': 0.06666667}
    _B3_SL     = 0.04
    _B3_TP     = 0.12

    def on_bar(self, symbol: str, bar: pd.Series) -> None:
        # ── Shared indicators ──────────────────────────────────────────────
        _advdec_ny_bars = self._data.get_latest_n_bars("ADVDEC.NY", 21)
        if _advdec_ny_bars is None or len(_advdec_ny_bars) < 21:
            return
        _sma_5_advdec_ny = compute_indicator("SMA", _advdec_ny_bars, 5)
        _sma_20_advdec_ny = compute_indicator("SMA", _advdec_ny_bars, 20)
        _ndx_bars = self._data.get_latest_n_bars("^NDX", 21)
        if _ndx_bars is None or len(_ndx_bars) < 21:
            return
        _raw_1_ndx = compute_indicator("RAW", _ndx_bars, 1)
        _ema_20_ndx = compute_indicator("EMA", _ndx_bars, 20)
        _cpi_yoy_prelim_bars = self._data.get_latest_n_bars("CPI_YOY_PRELIM", 5)
        if _cpi_yoy_prelim_bars is None or len(_cpi_yoy_prelim_bars) < 5:
            return
        _raw_1_cpi_yoy_prelim = compute_indicator("RAW", _cpi_yoy_prelim_bars, 1)
        _sma_4_cpi_yoy_prelim = compute_indicator("SMA", _cpi_yoy_prelim_bars, 4)
        _vix3m_vix_bars = self._data.get_latest_n_bars("VIX3M_VIX", 21)
        if _vix3m_vix_bars is None or len(_vix3m_vix_bars) < 21:
            return
        _raw_1_vix3m_vix = compute_indicator("RAW", _vix3m_vix_bars, 1)
        _ema_20_vix3m_vix = compute_indicator("EMA", _vix3m_vix_bars, 20)
        _bollinger_lower_20_vix3m_vix = compute_indicator("BOLLINGER_LOWER", _vix3m_vix_bars, 20)

        # ═══════════════════════════════════════════════════════════════════
        # BASKET 1  ·  AAPL, MSFT, ^NDX, ^GSPC  ·  size 80.0%  ·  SL —  ·  TP —
        # ═══════════════════════════════════════════════════════════════════
        if symbol in self._B1_ASSETS:

            # Snapshot
            _snapshot = {
                "SMA_5_ADVDEC.NY": round(_sma_5_advdec_ny, 4),
                "SMA_20_ADVDEC.NY": round(_sma_20_advdec_ny, 4),
                "RAW_1_^NDX": round(_raw_1_ndx, 4),
                "EMA_20_^NDX": round(_ema_20_ndx, 4),
                "RAW_1_CPI_YOY_PRELIM": round(_raw_1_cpi_yoy_prelim, 4),
                "SMA_4_CPI_YOY_PRELIM": round(_sma_4_cpi_yoy_prelim, 4),
                "RAW_1_VIX3M_VIX": round(_raw_1_vix3m_vix, 4),
                "EMA_20_VIX3M_VIX": round(_ema_20_vix3m_vix, 4),
                "BOLLINGER_LOWER_20_VIX3M_VIX": round(_bollinger_lower_20_vix3m_vix, 4),
            }

            # ─── Entry ────────────────────────────────────────────────────
            # SMA(5) [sur ADVDEC.NY]  >  SMA(20) [sur ADVDEC.NY]  [for 3 consecutive bars]
            _raw_0 = (_sma_5_advdec_ny > _sma_20_advdec_ny)
            if not hasattr(self, '_persist_b1_en_0'):
                self._persist_b1_en_0 = {}
            if _raw_0:
                self._persist_b1_en_0[symbol] = self._persist_b1_en_0.get(symbol, 0) + 1
            else:
                self._persist_b1_en_0[symbol] = 0
            _eff_0 = self._persist_b1_en_0.get(symbol, 0) >= 3
            _entry = (
                (_eff_0)
            )

            # ─── Exit  ────────────────────────────────────────────────────
            # RAW(1) [sur NDX]  <  EMA(20) [sur NDX]  [for 3 consecutive bars]
            _raw_0 = (_raw_1_ndx < _ema_20_ndx)
            if not hasattr(self, '_persist_b1_ex_0'):
                self._persist_b1_ex_0 = {}
            if _raw_0:
                self._persist_b1_ex_0[symbol] = self._persist_b1_ex_0.get(symbol, 0) + 1
            else:
                self._persist_b1_ex_0[symbol] = 0
            _eff_0 = self._persist_b1_ex_0.get(symbol, 0) >= 3
            _exit = (
                (_eff_0)
            )

            # ─── Signals ───────────────────────────────────────────────────
            if not hasattr(self, '_pd_b1'):
                self._pd_b1 = {}
            _dir = self._pd_b1.get(symbol)

            if not hasattr(self, '_prio_b1'):
                self._prio_b1 = {}
            if not hasattr(self, '_prev_b1'):
                self._prev_b1 = {}

            # Priority lock — first condition to turn True wins.
            # The other must wait until the first goes False.
            _prio_l     = self._prio_b1.get((symbol, 'l'))
            _entry_rose = _entry and not self._prev_b1.get((symbol, 'en'), False)
            _exit_rose  = _exit  and not self._prev_b1.get((symbol, 'ex'), False)
            if _prio_l == 'en' and not _entry:
                _prio_l = 'ex' if _exit else None
            elif _prio_l == 'ex' and not _exit:
                _prio_l = 'en' if _entry else None
            if _entry_rose and _prio_l is None:
                _prio_l = 'en'
            elif _exit_rose and _prio_l is None:
                _prio_l = 'ex'
            self._prio_b1[(symbol, 'l')] = _prio_l
            self._prev_b1[(symbol, 'en')] = bool(_entry)
            self._prev_b1[(symbol, 'ex')] = bool(_exit)

            if _prio_l == 'en':
                self._pd_b1[symbol] = "LONG"
                self.signal(symbol, "LONG", _snapshot,
                            position_size=self._B1_SIZES.get(symbol, self._B1_SIZES.get(list(self._B1_ASSETS)[0], 0.1)),
                            basket_id="basket_1",
                            basket_sl=self._B1_SL, basket_tp=self._B1_TP)
            elif _prio_l == 'ex' and _dir == "LONG":
                self._pd_b1[symbol] = None
                self.signal(symbol, "FLAT", _snapshot, basket_id="basket_1")

        # ═══════════════════════════════════════════════════════════════════
        # BASKET 2  ·  GC=F, CL=F  ·  size 60.0%  ·  SL —  ·  TP —
        # ═══════════════════════════════════════════════════════════════════
        if symbol in self._B2_ASSETS:

            # Snapshot
            _snapshot = {
                "SMA_5_ADVDEC.NY": round(_sma_5_advdec_ny, 4),
                "SMA_20_ADVDEC.NY": round(_sma_20_advdec_ny, 4),
                "RAW_1_^NDX": round(_raw_1_ndx, 4),
                "EMA_20_^NDX": round(_ema_20_ndx, 4),
                "RAW_1_CPI_YOY_PRELIM": round(_raw_1_cpi_yoy_prelim, 4),
                "SMA_4_CPI_YOY_PRELIM": round(_sma_4_cpi_yoy_prelim, 4),
                "RAW_1_VIX3M_VIX": round(_raw_1_vix3m_vix, 4),
                "EMA_20_VIX3M_VIX": round(_ema_20_vix3m_vix, 4),
                "BOLLINGER_LOWER_20_VIX3M_VIX": round(_bollinger_lower_20_vix3m_vix, 4),
            }

            # ─── Entry ────────────────────────────────────────────────────
            _entry = (
                (_raw_1_cpi_yoy_prelim > _sma_4_cpi_yoy_prelim)
            )

            # ─── Exit  ────────────────────────────────────────────────────
            _exit = (
                (_raw_1_cpi_yoy_prelim < _sma_4_cpi_yoy_prelim)
            )

            # ─── Signals ───────────────────────────────────────────────────
            if not hasattr(self, '_pd_b2'):
                self._pd_b2 = {}
            _dir = self._pd_b2.get(symbol)

            if not hasattr(self, '_prio_b2'):
                self._prio_b2 = {}
            if not hasattr(self, '_prev_b2'):
                self._prev_b2 = {}

            # Priority lock — first condition to turn True wins.
            # The other must wait until the first goes False.
            _prio_l     = self._prio_b2.get((symbol, 'l'))
            _entry_rose = _entry and not self._prev_b2.get((symbol, 'en'), False)
            _exit_rose  = _exit  and not self._prev_b2.get((symbol, 'ex'), False)
            if _prio_l == 'en' and not _entry:
                _prio_l = 'ex' if _exit else None
            elif _prio_l == 'ex' and not _exit:
                _prio_l = 'en' if _entry else None
            if _entry_rose and _prio_l is None:
                _prio_l = 'en'
            elif _exit_rose and _prio_l is None:
                _prio_l = 'ex'
            self._prio_b2[(symbol, 'l')] = _prio_l
            self._prev_b2[(symbol, 'en')] = bool(_entry)
            self._prev_b2[(symbol, 'ex')] = bool(_exit)

            if _prio_l == 'en':
                self._pd_b2[symbol] = "LONG"
                self.signal(symbol, "LONG", _snapshot,
                            position_size=self._B2_SIZES.get(symbol, self._B2_SIZES.get(list(self._B2_ASSETS)[0], 0.1)),
                            basket_id="basket_2",
                            basket_sl=self._B2_SL, basket_tp=self._B2_TP)
            elif _prio_l == 'ex' and _dir == "LONG":
                self._pd_b2[symbol] = None
                self.signal(symbol, "FLAT", _snapshot, basket_id="basket_2")

        # ═══════════════════════════════════════════════════════════════════
        # BASKET 3  ·  ^GSPC, ^NDX  ·  size 20.0%  ·  SL 4.0%  ·  TP 12.0%
        # ═══════════════════════════════════════════════════════════════════
        if symbol in self._B3_ASSETS:

            # Snapshot
            _snapshot = {
                "SMA_5_ADVDEC.NY": round(_sma_5_advdec_ny, 4),
                "SMA_20_ADVDEC.NY": round(_sma_20_advdec_ny, 4),
                "RAW_1_^NDX": round(_raw_1_ndx, 4),
                "EMA_20_^NDX": round(_ema_20_ndx, 4),
                "RAW_1_CPI_YOY_PRELIM": round(_raw_1_cpi_yoy_prelim, 4),
                "SMA_4_CPI_YOY_PRELIM": round(_sma_4_cpi_yoy_prelim, 4),
                "RAW_1_VIX3M_VIX": round(_raw_1_vix3m_vix, 4),
                "EMA_20_VIX3M_VIX": round(_ema_20_vix3m_vix, 4),
                "BOLLINGER_LOWER_20_VIX3M_VIX": round(_bollinger_lower_20_vix3m_vix, 4),
            }

            # ─── Short entry ───────────────────────────────────────────
            # RAW(1) [sur VIX3M_VIX]  <  1.08  [latch 3 bars]
            _raw_0 = (_raw_1_vix3m_vix < 1.08)
            if not hasattr(self, '_persist_b3_sh_0'):
                self._persist_b3_sh_0 = {}
            if _raw_0:
                self._persist_b3_sh_0[symbol] = self._persist_b3_sh_0.get(symbol, 0) + 1
            else:
                self._persist_b3_sh_0[symbol] = 0
            _trig_0 = self._persist_b3_sh_0.get(symbol, 0) >= 5
            if not hasattr(self, '_latch_b3_sh_0'):
                self._latch_b3_sh_0 = {}
            if _trig_0:
                self._latch_b3_sh_0[symbol] = 3
            elif symbol in self._latch_b3_sh_0:
                self._latch_b3_sh_0[symbol] -= 1
                if self._latch_b3_sh_0[symbol] <= 0:
                    del self._latch_b3_sh_0[symbol]
            _eff_0 = symbol in self._latch_b3_sh_0
            # RAW(1) [sur VIX3M_VIX]  <  EMA(20) [sur VIX3M_VIX]  [latch 2 bars]
            _raw_1 = (_raw_1_vix3m_vix < _ema_20_vix3m_vix)
            if not hasattr(self, '_latch_b3_sh_1'):
                self._latch_b3_sh_1 = {}
            if _raw_1:
                self._latch_b3_sh_1[symbol] = 2
            elif symbol in self._latch_b3_sh_1:
                self._latch_b3_sh_1[symbol] -= 1
                if self._latch_b3_sh_1[symbol] <= 0:
                    del self._latch_b3_sh_1[symbol]
            _eff_1 = symbol in self._latch_b3_sh_1
            _short_entry = (
                (_eff_0)
                and (_eff_1)
            )

            # ─── Cover exit ────────────────────────────────────────────
            _cover = (
                (_raw_1_vix3m_vix < _bollinger_lower_20_vix3m_vix)
            )

            # ─── Signals ───────────────────────────────────────────────────
            if not hasattr(self, '_pd_b3'):
                self._pd_b3 = {}
            _dir = self._pd_b3.get(symbol)

            if not hasattr(self, '_prio_b3'):
                self._prio_b3 = {}
            if not hasattr(self, '_prev_b3'):
                self._prev_b3 = {}


            _prio_s      = self._prio_b3.get((symbol, 's'))
            _short_rose  = _short_entry and not self._prev_b3.get((symbol, 'sh'), False)
            _cover_rose  = _cover       and not self._prev_b3.get((symbol, 'cv'), False)
            if _prio_s == 'sh' and not _short_entry:
                _prio_s = 'cv' if _cover else None
            elif _prio_s == 'cv' and not _cover:
                _prio_s = 'sh' if _short_entry else None
            if _short_rose and _prio_s is None:
                _prio_s = 'sh'
            elif _cover_rose and _prio_s is None:
                _prio_s = 'cv'
            self._prio_b3[(symbol, 's')] = _prio_s
            self._prev_b3[(symbol, 'sh')] = bool(_short_entry)
            self._prev_b3[(symbol, 'cv')] = bool(_cover)

            if _prio_s == 'sh':
                self._pd_b3[symbol] = "SHORT"
                self.signal(symbol, "SHORT", _snapshot,
                            position_size=self._B3_SIZES.get(symbol, self._B3_SIZES.get(list(self._B3_ASSETS)[0], 0.1)),
                            basket_id="basket_3",
                            basket_sl=self._B3_SL, basket_tp=self._B3_TP)
            elif _prio_s == 'cv' and _dir == "SHORT":
                self._pd_b3[symbol] = None
                self.signal(symbol, "COVER", _snapshot, basket_id="basket_3")

