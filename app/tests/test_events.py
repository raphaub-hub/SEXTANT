"""
tests/test_events.py — Tests unitaires des événements et de la queue.
"""

import pytest
from datetime import datetime

from backtest.core.events import (
    Direction, EventType, FillEvent, MarketEvent,
    OrderEvent, OrderSide, OrderType, SignalEvent,
)
from backtest.core.queue import EventQueue


NOW = datetime(2023, 1, 2, 9, 30)


class TestEvents:
    def test_market_event_type(self):
        e = MarketEvent(timestamp=NOW, symbols=["AAPL"])
        assert e.type == EventType.MARKET
        assert e.symbols == ["AAPL"]

    def test_signal_event_type(self):
        e = SignalEvent(
            timestamp=NOW, strategy_id="s1", symbol="AAPL",
            direction=Direction.LONG, position_size=0.1,
        )
        assert e.type == EventType.SIGNAL
        assert e.direction == Direction.LONG

    def test_order_event_type(self):
        e = OrderEvent(
            timestamp=NOW, symbol="AAPL",
            order_type=OrderType.MARKET, side=OrderSide.BUY, quantity=10.0,
        )
        assert e.type == EventType.ORDER
        assert e.side == OrderSide.BUY

    def test_fill_event_notional(self):
        e = FillEvent(
            timestamp=NOW, symbol="AAPL", side=OrderSide.BUY,
            quantity=10.0, fill_price=150.0, commission=1.5,
        )
        assert e.type == EventType.FILL
        assert e.notional == pytest.approx(1500.0)
        assert e.total_cost == pytest.approx(1501.5)

    def test_direction_from_string(self):
        assert Direction["LONG"]  == Direction.LONG
        assert Direction["SHORT"] == Direction.SHORT
        assert Direction["FLAT"]  == Direction.FLAT


class TestEventQueue:
    def test_fifo_order(self):
        q = EventQueue()
        e1 = MarketEvent(timestamp=NOW, symbols=["AAPL"])
        e2 = MarketEvent(timestamp=NOW, symbols=["MSFT"])
        q.put(e1)
        q.put(e2)
        assert q.get() is e1
        assert q.get() is e2

    def test_empty(self):
        q = EventQueue()
        assert q.empty()
        q.put(MarketEvent(timestamp=NOW, symbols=[]))
        assert not q.empty()

    def test_len(self):
        q = EventQueue()
        assert len(q) == 0
        q.put(MarketEvent(timestamp=NOW, symbols=[]))
        assert len(q) == 1

    def test_get_empty_raises(self):
        q = EventQueue()
        with pytest.raises(IndexError):
            q.get()
