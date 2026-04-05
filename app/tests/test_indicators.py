"""
tests/test_indicators.py — Tests unitaires des indicateurs techniques.
"""

import pytest
import numpy as np
import pandas as pd

from backtest.strategy.indicators import (
    compute_indicator, register_indicator, get_available_indicators,
)


def make_bars(closes: list[float], highs=None, lows=None, volumes=None) -> pd.DataFrame:
    n = len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    if volumes is None:
        volumes = [1_000_000] * n
    return pd.DataFrame({
        "open":   closes,
        "high":   highs,
        "low":    lows,
        "close":  closes,
        "volume": volumes,
    })


class TestSMA:
    def test_flat_series(self):
        bars = make_bars([100.0] * 20)
        result = compute_indicator("SMA", bars, 10)
        assert result == pytest.approx(100.0)

    def test_known_value(self):
        bars = make_bars(list(range(1, 11)))  # 1..10, SMA(5) = 8.0
        result = compute_indicator("SMA", bars, 5)
        assert result == pytest.approx(8.0)

    def test_not_enough_bars(self):
        bars = make_bars([100.0] * 3)
        with pytest.raises(ValueError):
            compute_indicator("SMA", bars, 10)


class TestEMA:
    def test_flat_series(self):
        bars = make_bars([50.0] * 30)
        result = compute_indicator("EMA", bars, 10)
        assert result == pytest.approx(50.0, rel=1e-4)


class TestRSI:
    def test_all_gains(self):
        """RSI doit être proche de 100 si toutes les barres montent."""
        closes = [float(i) for i in range(1, 30)]
        bars = make_bars(closes)
        result = compute_indicator("RSI", bars, 14)
        assert result > 90.0

    def test_all_losses(self):
        """RSI doit être proche de 0 si toutes les barres baissent."""
        closes = [float(30 - i) for i in range(30)]
        bars = make_bars(closes)
        result = compute_indicator("RSI", bars, 14)
        assert result < 10.0

    def test_range(self):
        closes = [100 + 10 * np.sin(i * 0.3) for i in range(50)]
        bars = make_bars(closes)
        result = compute_indicator("RSI", bars, 14)
        assert 0.0 <= result <= 100.0


class TestATR:
    def test_constant_range(self):
        highs  = [110.0] * 20
        lows   = [90.0]  * 20
        closes = [100.0] * 20
        bars = make_bars(closes, highs=highs, lows=lows)
        result = compute_indicator("ATR", bars, 10)
        assert result == pytest.approx(20.0, rel=0.01)


class TestCustomIndicator:
    def test_register_and_use(self):
        def always_42(bars: pd.DataFrame, period: int) -> float:
            return 42.0

        register_indicator("ALWAYS_42", always_42)
        bars = make_bars([100.0] * 10)
        assert compute_indicator("ALWAYS_42", bars, 5) == 42.0
        assert "ALWAYS_42" in get_available_indicators()

    def test_case_insensitive(self):
        bars = make_bars([100.0] * 20)
        r1 = compute_indicator("sma", bars, 10)
        r2 = compute_indicator("SMA", bars, 10)
        assert r1 == r2

    def test_unknown_indicator(self):
        bars = make_bars([100.0] * 10)
        with pytest.raises(ValueError, match="Indicateur inconnu"):
            compute_indicator("UNKNOWN_XYZ", bars, 5)
