from __future__ import annotations

from backend.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    Ticker,
    Trade,
)


class TestSignal:
    def test_buy_signal_fields(self):
        signal = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.85,
            strategy_name="rsi",
            reason="RSI below 30",
            indicators={"rsi": 28.5},
        )

        assert signal.direction == "BUY"
        assert signal.confidence == 0.85
        assert signal.indicators["rsi"] == 28.5

    def test_hold_signal_default_indicators(self):
        signal = Signal(
            symbol="ETH/USDT",
            direction="HOLD",
            confidence=0.0,
            strategy_name="macd",
            reason="No clear signal",
        )

        assert signal.indicators == {}


class TestOrder:
    def test_market_buy_order(self):
        order = Order(
            id="test-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            amount=0.01,
            price=None,
            status=OrderStatus.OPEN,
        )

        assert order.side == OrderSide.BUY
        assert order.filled_amount == 0.0

    def test_filled_order_has_fill_price(self):
        order = Order(
            id="test-2",
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            amount=1.0,
            price=3500.0,
            status=OrderStatus.FILLED,
            filled_amount=1.0,
            filled_price=3500.0,
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_price == 3500.0


class TestTicker:
    def test_ticker_spread(self):
        ticker = Ticker(symbol="BTC/USDT", bid=65000.0, ask=65010.0, last=65005.0)
        spread = ticker.ask - ticker.bid

        assert spread == 10.0


class TestPosition:
    def test_unrealized_pnl_calculation(self):
        pos = Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.1,
            entry_price=60000.0,
            current_price=65000.0,
            unrealized_pnl=500.0,
        )

        assert pos.unrealized_pnl == 500.0
        assert pos.entry_price < pos.current_price


class TestTrade:
    def test_trade_with_signal(self):
        signal = Signal(
            symbol="BTC/USDT",
            direction="BUY",
            confidence=0.9,
            strategy_name="rsi",
            reason="Oversold",
        )
        trade = Trade(
            id="t-1",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            amount=0.01,
            price=65000.0,
            fee=6.5,
            signal=signal,
        )

        assert trade.signal is not None
        assert trade.signal.strategy_name == "rsi"
        assert trade.fee == 6.5
