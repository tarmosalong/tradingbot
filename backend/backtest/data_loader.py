from __future__ import annotations

from datetime import datetime
from pathlib import Path

import ccxt.async_support as ccxt_async
import pandas as pd

from backend.core.logger import get_logger

logger = get_logger("data_loader")

BATCH_SIZE = 1000


async def load_from_binance(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch historical OHLCV data from Binance, paginating in batches."""
    exchange = ccxt_async.binance({"enableRateLimit": True})

    try:
        all_rows: list[list] = []
        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        while since_ms < end_ms:
            batch = await exchange.fetch_ohlcv(
                symbol,
                timeframe=timeframe,
                since=since_ms,
                limit=BATCH_SIZE,
            )
            if not batch:
                break

            all_rows.extend(batch)
            last_ts = batch[-1][0]

            if last_ts >= end_ms:
                break
            since_ms = last_ts + 1

            logger.debug(
                "Loaded batch",
                symbol=symbol,
                rows=len(batch),
                total=len(all_rows),
            )
    finally:
        await exchange.close()

    if not all_rows:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )

    df = pd.DataFrame(
        all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    end_ts = pd.Timestamp(end)
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    df = df[df["timestamp"] <= end_ts]
    df = df.drop_duplicates(subset="timestamp").reset_index(drop=True)

    logger.info(
        "Loaded historical data",
        symbol=symbol,
        timeframe=timeframe,
        rows=len(df),
        start=str(df["timestamp"].iloc[0]),
        end=str(df["timestamp"].iloc[-1]),
    )
    return df


def load_from_csv(path: str | Path) -> pd.DataFrame:
    """Load OHLCV data from a CSV file."""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    if df["timestamp"].dt.tz is None:
        df["timestamp"] = df["timestamp"].dt.tz_localize("UTC")
    return df


def save_to_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Save OHLCV data to CSV for caching."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("Saved data to CSV", path=str(path), rows=len(df))
