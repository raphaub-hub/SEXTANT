"""
tests/test_risk.py — Tests du StandardRiskManager.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from backtest.core.events import Direction, OrderSide, SignalEvent
from backtest.portfolio.position import Position
from backtest.risk.rules import StandardRiskManager


NOW = datetime(2023, 6, 1)


def make_signal(
    direction=Direction.LONG,
    position_size=0.1,
    stop_loss=0.02,
    take_profit=0.05,
    symbol="AAPL",
) -> SignalEvent:
    return SignalEvent(
        timestamp=NOW, strategy_id="test", symbol=symbol,
        direction=direction, position_size=position_size,
        stop_loss=stop_loss, take_profit=take_profit,
    )


def make_bar(close: float = 100.0) -> pd.Series:
    bar = pd.Series({"open": close, "high": close*1.01, "low": close*0.99,
                     "close": close, "volume": 1e6})
    bar.name = NOW
    return bar


def make_portfolio(equity=10_000.0, positions=None):
    pf = MagicMock()
    pf.equity = equity
    _long = positions or {}
    pf.long_positions  = _long
    pf.short_positions = {}
    pf.positions       = _long
    pf.basket_params   = {}
    pf.basket_entries  = {}
    return pf


class TestValidateOrder:
    def test_long_signal_no_position(self):
        risk = StandardRiskManager()
        orders = risk.validate_order(
            make_signal(Direction.LONG, position_size=0.1),
            make_portfolio(equity=10_000.0),
            make_bar(close=100.0),
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.BUY
        # quantity = 10_000 * 0.1 / 100 = 10
        assert orders[0].quantity == pytest.approx(10.0)

    def test_long_signal_already_long_ignored(self):
        risk = StandardRiskManager()
        pos = Position("AAPL", Direction.LONG, 10.0, 100.0, NOW)
        orders = risk.validate_order(
            make_signal(Direction.LONG),
            make_portfolio(positions={"AAPL": pos}),
            make_bar(100.0),
        )
        assert orders == []

    def test_flat_signal_with_long_position(self):
        risk = StandardRiskManager()
        pos = Position("AAPL", Direction.LONG, 10.0, 100.0, NOW)
        orders = risk.validate_order(
            make_signal(Direction.FLAT),
            make_portfolio(positions={"AAPL": pos}),
            make_bar(100.0),
        )
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        assert orders[0].quantity == 10.0

    def test_flat_signal_no_position_returns_none(self):
        risk = StandardRiskManager()
        orders = risk.validate_order(
            make_signal(Direction.FLAT),
            make_portfolio(),
            make_bar(),
        )
        assert orders == []

    def test_stop_loss_price_computed(self):
        risk = StandardRiskManager()
        orders = risk.validate_order(
            make_signal(Direction.LONG, stop_loss=0.02),
            make_portfolio(equity=10_000.0),
            make_bar(close=100.0),
        )
        assert orders[0].stop_loss_price == pytest.approx(98.0)

    def test_take_profit_price_computed(self):
        risk = StandardRiskManager()
        orders = risk.validate_order(
            make_signal(Direction.LONG, take_profit=0.05),
            make_portfolio(equity=10_000.0),
            make_bar(close=100.0),
        )
        assert orders[0].take_profit_price == pytest.approx(105.0)

    def test_no_bar_returns_none(self):
        risk = StandardRiskManager()
        orders = risk.validate_order(make_signal(), make_portfolio(), bar=None)
        assert orders == []


class TestCheckExits:
    def test_stop_loss_triggers(self):
        risk = StandardRiskManager()
        pos = Position("AAPL", Direction.LONG, 10.0, 100.0, NOW,
                       stop_loss_price=95.0)
        pf = make_portfolio(positions={"AAPL": pos})
        bar = make_bar(close=94.0)   # En dessous du stop

        orders = risk.check_exits(pf, {"AAPL": bar})
        assert len(orders) == 1
        assert orders[0].side == OrderSide.SELL
        assert "stop_loss" in orders[0].signal_ref.indicator_snapshot.get("_exit_reason", "")

    def test_take_profit_triggers(self):
        risk = StandardRiskManager()
        pos = Position("AAPL", Direction.LONG, 10.0, 100.0, NOW,
                       take_profit_price=110.0)
        pf = make_portfolio(positions={"AAPL": pos})
        bar = make_bar(close=111.0)   # Au-dessus du TP

        orders = risk.check_exits(pf, {"AAPL": bar})
        assert len(orders) == 1
        assert "take_profit" in orders[0].signal_ref.indicator_snapshot.get("_exit_reason", "")

    def test_no_exit_when_price_in_range(self):
        risk = StandardRiskManager()
        pos = Position("AAPL", Direction.LONG, 10.0, 100.0, NOW,
                       stop_loss_price=95.0, take_profit_price=110.0)
        pf = make_portfolio(positions={"AAPL": pos})
        bar = make_bar(close=102.0)   # Dans la plage

        orders = risk.check_exits(pf, {"AAPL": bar})
        assert len(orders) == 0
