"""
strategy/indicators.py — Registre extensible d'indicateurs techniques.

Tous les indicateurs opèrent sur un DataFrame de barres passées (no look-ahead).
La signature standard est : fn(bars: pd.DataFrame, period: int) -> float

Pour ajouter un indicateur custom :
    from backtest.strategy.indicators import register_indicator

    def my_ind(bars: pd.DataFrame, period: int) -> float:
        return bars["close"].iloc[-period:].pct_change().std()

    register_indicator("VOLATILITY", my_ind)

L'indicateur est ensuite disponible dans toute stratégie via :
    self.indicator("VOLATILITY", 20)
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd


IndicatorFn = Callable[[pd.DataFrame, int], float]

_REGISTRY: dict[str, IndicatorFn] = {}


def register_indicator(name: str, fn: IndicatorFn) -> None:
    """Enregistre un indicateur. name est insensible à la casse."""
    _REGISTRY[name.upper()] = fn


def get_available_indicators() -> list[str]:
    return sorted(_REGISTRY.keys())


def compute_indicator(name: str, bars: pd.DataFrame, period: int) -> float:
    """
    Calcule l'indicateur sur les barres fournies.
    Lève ValueError si l'indicateur est inconnu ou si les données sont insuffisantes.
    """
    key = name.upper()
    if key not in _REGISTRY:
        raise ValueError(
            f"Indicateur inconnu : '{name}'. "
            f"Disponibles : {get_available_indicators()}"
        )
    if len(bars) < period:
        raise ValueError(
            f"Pas assez de barres pour {name}({period}) : "
            f"{len(bars)} disponibles, {period} nécessaires."
        )
    return _REGISTRY[key](bars, period)


# ---------------------------------------------------------------------------
# Indicateurs built-in
# ---------------------------------------------------------------------------

def _sma(bars: pd.DataFrame, period: int) -> float:
    """Simple Moving Average — moyenne des `period` derniers closes."""
    return float(bars["close"].iloc[-period:].mean())


def _ema(bars: pd.DataFrame, period: int) -> float:
    """Exponential Moving Average."""
    return float(bars["close"].ewm(span=period, adjust=False).mean().iloc[-1])


def _rsi(bars: pd.DataFrame, period: int) -> float:
    """Relative Strength Index (Wilder, 0–100)."""
    closes = bars["close"].iloc[-(period + 1):]
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).mean()
    loss = (-delta.clip(upper=0)).mean()
    if loss == 0.0:
        return 100.0
    rs = gain / loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _atr(bars: pd.DataFrame, period: int) -> float:
    """Average True Range."""
    needed = bars.iloc[-(period + 1):]
    high  = needed["high"]
    low   = needed["low"]
    close_prev = needed["close"].shift(1)

    tr = pd.concat([
        high - low,
        (high - close_prev).abs(),
        (low  - close_prev).abs(),
    ], axis=1).max(axis=1).dropna()

    return float(tr.iloc[-period:].mean())


def _bollinger_upper(bars: pd.DataFrame, period: int) -> float:
    """Bande de Bollinger supérieure (mean + 2σ)."""
    closes = bars["close"].iloc[-period:]
    return float(closes.mean() + 2.0 * closes.std(ddof=0))


def _bollinger_lower(bars: pd.DataFrame, period: int) -> float:
    """Bande de Bollinger inférieure (mean - 2σ)."""
    closes = bars["close"].iloc[-period:]
    return float(closes.mean() - 2.0 * closes.std(ddof=0))


def _bollinger_mid(bars: pd.DataFrame, period: int) -> float:
    """Bande de Bollinger médiane (SMA)."""
    return _sma(bars, period)


def _stoch_k(bars: pd.DataFrame, period: int) -> float:
    """Stochastique %K."""
    closes = bars["close"].iloc[-period:]
    highs  = bars["high"].iloc[-period:]
    lows   = bars["low"].iloc[-period:]
    lowest  = lows.min()
    highest = highs.max()
    if highest == lowest:
        return 50.0
    return float(100.0 * (closes.iloc[-1] - lowest) / (highest - lowest))


def _momentum(bars: pd.DataFrame, period: int) -> float:
    """Momentum : close courant / close il y a `period` barres."""
    closes = bars["close"]
    if len(closes) < period + 1:
        raise ValueError(f"Momentum({period}) : pas assez de barres.")
    return float(closes.iloc[-1] / closes.iloc[-(period + 1)])


def _roc(bars: pd.DataFrame, period: int) -> float:
    """Rate of Change en % : (close - close[n]) / close[n] * 100."""
    closes = bars["close"]
    if len(closes) < period + 1:
        raise ValueError(f"ROC({period}) : pas assez de barres.")
    prev = closes.iloc[-(period + 1)]
    if prev == 0.0:
        return 0.0
    return float((closes.iloc[-1] - prev) / prev * 100.0)


def _highest_high(bars: pd.DataFrame, period: int) -> float:
    """Plus haut des `period` dernières barres."""
    return float(bars["high"].iloc[-period:].max())


def _lowest_low(bars: pd.DataFrame, period: int) -> float:
    """Plus bas des `period` dernières barres."""
    return float(bars["low"].iloc[-period:].min())


def _vwap(bars: pd.DataFrame, period: int) -> float:
    """Volume Weighted Average Price."""
    recent = bars.iloc[-period:]
    typical = (recent["high"] + recent["low"] + recent["close"]) / 3.0
    vol = recent.get("volume", pd.Series(np.ones(len(recent))))
    if vol.sum() == 0:
        return float(typical.mean())
    return float((typical * vol).sum() / vol.sum())


def _raw(bars: pd.DataFrame, period: int) -> float:
    """RAW / CLOSE — valeur brute du dernier close (period ignoree)."""
    return float(bars["close"].iloc[-1])


def _volume(bars: pd.DataFrame, period: int) -> float:
    """VOLUME — volume de la dernière barre (period ignoree)."""
    if "volume" in bars.columns:
        return float(bars["volume"].iloc[-1])
    return 0.0


def _open(bars: pd.DataFrame, period: int) -> float:
    """OPEN — prix d'ouverture de la dernière barre (period ignoree)."""
    return float(bars["open"].iloc[-1])


def _high(bars: pd.DataFrame, period: int) -> float:
    """HIGH — plus haut de la dernière barre / séance (period ignoree)."""
    return float(bars["high"].iloc[-1])


def _low(bars: pd.DataFrame, period: int) -> float:
    """LOW — plus bas de la dernière barre / séance (period ignoree)."""
    return float(bars["low"].iloc[-1])


# Enregistrement
register_indicator("RAW",            _raw)
register_indicator("VOLUME",         _volume)
register_indicator("OPEN",           _open)
register_indicator("HIGH",           _high)
register_indicator("LOW",            _low)
register_indicator("SMA",             _sma)
register_indicator("EMA",             _ema)
register_indicator("RSI",             _rsi)
register_indicator("ATR",             _atr)
register_indicator("BOLLINGER_UPPER", _bollinger_upper)
register_indicator("BOLLINGER_LOWER", _bollinger_lower)
register_indicator("BOLLINGER_MID",   _bollinger_mid)
register_indicator("STOCH_K",         _stoch_k)
register_indicator("MOMENTUM",        _momentum)
register_indicator("ROC",             _roc)
register_indicator("HIGHEST_HIGH",    _highest_high)
register_indicator("LOWEST_LOW",      _lowest_low)
register_indicator("VWAP",            _vwap)
