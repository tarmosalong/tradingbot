from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"


class OrderStatus(StrEnum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class Ticker:
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    amount: float
    price: float | None
    status: OrderStatus
    filled_amount: float = 0.0
    filled_price: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Signal:
    symbol: str
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    strategy_name: str
    reason: str
    indicators: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Position:
    symbol: str
    side: OrderSide
    amount: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None
    trailing_stop: float | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Trade:
    id: str
    symbol: str
    side: OrderSide
    amount: float
    price: float
    fee: float = 0.0
    pnl: float | None = None
    signal: Signal | None = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
