from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from backend.models import Order, OrderSide, OrderStatus, OrderType, Signal, Trade

_DB_PATH = Path(__file__).resolve().parent.parent / "tradingbot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    pnl REAL,
    signal_json TEXT,
    executed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL,
    filled_amount REAL NOT NULL DEFAULT 0,
    filled_price REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    total_value_usdt REAL NOT NULL,
    balances_json TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    strategy_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    indicators_json TEXT,
    timestamp TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signal_log_ts ON signal_log(timestamp DESC);
"""


class Database:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = str(db_path or _DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def insert_trade(self, trade: Trade) -> None:
        conn = self._ensure_connected()
        signal_json = None
        if trade.signal:
            signal_json = json.dumps({
                "symbol": trade.signal.symbol,
                "direction": trade.signal.direction,
                "confidence": trade.signal.confidence,
                "strategy_name": trade.signal.strategy_name,
                "reason": trade.signal.reason,
                "indicators": trade.signal.indicators,
            })
        sql = (
            "INSERT INTO trades"
            " (id, symbol, side, amount, price, fee, pnl, signal_json, executed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        await conn.execute(
            sql,
            (
                trade.id,
                trade.symbol,
                trade.side.value,
                trade.amount,
                trade.price,
                trade.fee,
                trade.pnl,
                signal_json,
                trade.executed_at.isoformat(),
            ),
        )
        await conn.commit()

    async def insert_order(self, order: Order) -> None:
        conn = self._ensure_connected()
        sql = (
            "INSERT OR REPLACE INTO orders"
            " (id, symbol, side, order_type, amount, price, status,"
            " filled_amount, filled_price, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        await conn.execute(
            sql,
            (
                order.id,
                order.symbol,
                order.side.value,
                order.order_type.value,
                order.amount,
                order.price,
                order.status.value,
                order.filled_amount,
                order.filled_price,
                order.created_at.isoformat(),
                order.updated_at.isoformat(),
            ),
        )
        await conn.commit()

    async def get_trades(self, symbol: str | None = None, limit: int = 100) -> list[Trade]:
        conn = self._ensure_connected()
        if symbol:
            cursor = await conn.execute(
                "SELECT * FROM trades WHERE symbol = ? ORDER BY executed_at DESC LIMIT ?",
                (symbol, limit),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_trade(row) for row in rows]

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        conn = self._ensure_connected()
        if symbol:
            cursor = await conn.execute(
                "SELECT * FROM orders WHERE status = 'OPEN'"
                " AND symbol = ? ORDER BY created_at DESC",
                (symbol,),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM orders WHERE status = 'OPEN' ORDER BY created_at DESC",
            )
        rows = await cursor.fetchall()
        return [self._row_to_order(row) for row in rows]

    async def save_portfolio_snapshot(self, total_value: float, balances: dict[str, float]) -> None:
        conn = self._ensure_connected()
        sql = (
            "INSERT INTO portfolio_snapshots"
            " (total_value_usdt, balances_json, timestamp)"
            " VALUES (?, ?, ?)"
        )
        await conn.execute(
            sql,
            (total_value, json.dumps(balances), datetime.now(UTC).isoformat()),
        )
        await conn.commit()

    async def get_portfolio_history(self, limit: int = 500) -> list[dict]:
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "SELECT total_value_usdt, balances_json, timestamp FROM portfolio_snapshots "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "total_value_usdt": row["total_value_usdt"],
                "balances": json.loads(row["balances_json"]),
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    async def insert_signal(self, signal: Signal) -> None:
        conn = self._ensure_connected()
        indicators_json = json.dumps(signal.indicators) if signal.indicators else None
        await conn.execute(
            "INSERT INTO signal_log"
            " (symbol, direction, confidence, strategy_name, reason,"
            "  indicators_json, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                signal.symbol,
                signal.direction,
                signal.confidence,
                signal.strategy_name,
                signal.reason,
                indicators_json,
                signal.timestamp.isoformat(),
            ),
        )
        await conn.commit()

    async def get_signals(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        conn = self._ensure_connected()
        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if strategy:
            clauses.append("strategy_name = ?")
            params.append(strategy)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        cursor = await conn.execute(
            f"SELECT * FROM signal_log{where} ORDER BY timestamp DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "symbol": row["symbol"],
                "direction": row["direction"],
                "confidence": row["confidence"],
                "strategy_name": row["strategy_name"],
                "reason": row["reason"],
                "indicators": json.loads(row["indicators_json"])
                if row["indicators_json"]
                else {},
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    async def get_net_positions(self) -> list[dict]:
        """Reconstruct open positions from trade history.

        Computes net holdings per symbol using weighted average
        entry price across all BUY/SELL trades.
        """
        conn = self._ensure_connected()
        cursor = await conn.execute(
            "SELECT symbol, side, amount, price, executed_at"
            " FROM trades ORDER BY executed_at ASC",
        )
        rows = await cursor.fetchall()

        positions: dict[str, dict] = {}
        for row in rows:
            symbol = row["symbol"]
            side = row["side"]
            amount = row["amount"]
            price = row["price"]
            ts = row["executed_at"]

            if symbol not in positions:
                positions[symbol] = {
                    "amount": 0.0,
                    "cost_basis": 0.0,
                    "peak_price": 0.0,
                    "opened_at": ts,
                }

            pos = positions[symbol]
            if side == "BUY":
                new_cost = pos["cost_basis"] + (amount * price)
                pos["amount"] += amount
                pos["cost_basis"] = new_cost
                if price > pos["peak_price"]:
                    pos["peak_price"] = price
            elif side == "SELL":
                if pos["amount"] > 0:
                    ratio = min(amount / pos["amount"], 1.0)
                    pos["cost_basis"] *= (1.0 - ratio)
                pos["amount"] -= amount

        result = []
        for symbol, pos in positions.items():
            if pos["amount"] > 1e-10:
                entry = (
                    pos["cost_basis"] / pos["amount"]
                    if pos["amount"] > 0
                    else 0.0
                )
                result.append({
                    "symbol": symbol,
                    "amount": pos["amount"],
                    "entry_price": entry,
                    "peak_price": pos["peak_price"],
                    "opened_at": pos["opened_at"],
                })
        return result

    @staticmethod
    def _row_to_trade(row: aiosqlite.Row) -> Trade:
        return Trade(
            id=row["id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            amount=row["amount"],
            price=row["price"],
            fee=row["fee"],
            pnl=row["pnl"],
            executed_at=datetime.fromisoformat(row["executed_at"]),
        )

    @staticmethod
    def _row_to_order(row: aiosqlite.Row) -> Order:
        return Order(
            id=row["id"],
            symbol=row["symbol"],
            side=OrderSide(row["side"]),
            order_type=OrderType(row["order_type"]),
            amount=row["amount"],
            price=row["price"],
            status=OrderStatus(row["status"]),
            filled_amount=row["filled_amount"],
            filled_price=row["filled_price"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
