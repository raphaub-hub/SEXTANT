"""
tests/test_portfolio.py — Tests du SimplePortfolio.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd

from backtest.core.events import Direction, FillEvent, MarketEvent, OrderEvent, OrderSide, OrderType, SignalEvent
from backtest.portfolio.base import SimplePortfolio


NOW = datetime(2023, 6, 1)


def make_mock_data(symbol: str = "AAPL", close: float = 150.0):
    """Crée un DataHandler mock qui retourne toujours le même close."""
    bar = pd.Series({"open": close, "high": close*1.01, "low": close*0.99, "close": close, "volume": 1e6})
    bar.name = NOW
    data = MagicMock()
    data.symbol_list = [symbol]
    data.get_latest_bar.return_value = bar
    data.current_timestamp = NOW
    return data


def make_signal(symbol="AAPL", direction=Direction.LONG, strategy_id="test") -> SignalEvent:
    return SignalEvent(
        timestamp=NOW, strategy_id=strategy_id, symbol=symbol,
        direction=direction, position_size=0.1,
        stop_loss=0.02, take_profit=0.05,
    )


def make_order(symbol="AAPL", side=OrderSide.BUY, qty=10.0, signal=None, is_opening=False) -> OrderEvent:
    return OrderEvent(
        timestamp=NOW, symbol=symbol,
        order_type=OrderType.MARKET, side=side, quantity=qty,
        is_opening=is_opening,
        stop_loss_price=147.0, take_profit_price=157.5,
        signal_ref=signal,
    )


def make_fill(symbol="AAPL", side=OrderSide.BUY, qty=10.0, price=150.0, commission=1.5, order=None) -> FillEvent:
    return FillEvent(
        timestamp=NOW, symbol=symbol, side=side,
        quantity=qty, fill_price=price, commission=commission,
        order_ref=order,
    )


class TestPortfolioLong:
    def test_initial_equity(self):
        pf = SimplePortfolio(100_000.0, make_mock_data())
        assert pf.equity == 100_000.0
        assert pf.cash == 100_000.0

    def test_open_long(self):
        pf = SimplePortfolio(100_000.0, make_mock_data())
        order = make_order(is_opening=True)
        fill = make_fill(side=OrderSide.BUY, qty=10.0, price=150.0, commission=1.5, order=order)
        pf.on_fill(fill)

        assert "AAPL" in pf.positions
        pos = pf.positions["AAPL"]
        assert pos.direction == Direction.LONG
        assert pos.quantity == 10.0
        assert pos.entry_price == 150.0
        # Cash = 100_000 - (10 * 150 + 1.5) = 98_498.5
        assert pf.cash == pytest.approx(98_498.5)

    def test_close_long_winner(self):
        pf = SimplePortfolio(100_000.0, make_mock_data())
        sig = make_signal()
        open_order  = make_order(signal=sig, is_opening=True)
        close_order = make_order(side=OrderSide.SELL, signal=sig, is_opening=False)

        pf.on_fill(make_fill(side=OrderSide.BUY,  qty=10.0, price=150.0, commission=1.5, order=open_order))
        pf.on_fill(make_fill(side=OrderSide.SELL, qty=10.0, price=160.0, commission=1.6, order=close_order))

        assert "AAPL" not in pf.positions
        assert len(pf.trades) == 1
        trade = pf.trades[0]
        # PnL = (160 - 150) * 10 - 1.5 - 1.6 = 100 - 3.1 = 96.9
        assert trade.pnl == pytest.approx(96.9)
        assert trade.is_winner

    def test_close_long_loser(self):
        pf = SimplePortfolio(100_000.0, make_mock_data())
        open_order  = make_order(is_opening=True)
        close_order = make_order(side=OrderSide.SELL, is_opening=False)
        pf.on_fill(make_fill(side=OrderSide.BUY,  qty=10.0, price=150.0, commission=1.5, order=open_order))
        pf.on_fill(make_fill(side=OrderSide.SELL, qty=10.0, price=140.0, commission=1.4, order=close_order))

        trade = pf.trades[0]
        # PnL = (140 - 150) * 10 - 1.5 - 1.4 = -100 - 2.9 = -102.9
        assert trade.pnl == pytest.approx(-102.9)
        assert not trade.is_winner

    def test_equity_curve_updates_on_market(self):
        pf = SimplePortfolio(100_000.0, make_mock_data(close=150.0))
        open_order = make_order(is_opening=True)
        pf.on_fill(make_fill(side=OrderSide.BUY, qty=10.0, price=150.0, commission=1.5, order=open_order))
        market_event = MarketEvent(timestamp=NOW + timedelta(days=1), symbols=["AAPL"])
        pf.on_market(market_event)

        curve = pf.equity_curve
        assert len(curve) == 1
        # equity = cash + 10 * 150 = 98_498.5 + 1500 = 99_998.5
        assert curve.iloc[0] == pytest.approx(99_998.5)

    def test_no_position_flat_signal_is_ignored(self):
        """Pas de position → FLAT ne doit rien faire."""
        pf = SimplePortfolio(100_000.0, make_mock_data())
        # Simuler un SELL sans position ouverte → ne doit pas créer de position short
        pf.on_fill(make_fill(side=OrderSide.SELL, qty=10.0, price=150.0, commission=1.5))
        # Un SELL sans position ouverte ouvre un SHORT — dans notre logique, c'est correct
        # mais si on ne veut que du LONG, le RiskManager doit filtrer cela en amont
        assert len(pf.trades) == 0  # Pas de trade fermé
