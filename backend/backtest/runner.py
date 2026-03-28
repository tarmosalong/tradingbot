"""CLI entry point for running backtests.

Usage:
    python -m backend.backtest.runner --symbol BTC/USDT --timeframe 1h \
        --start 2025-01-01 --end 2025-12-31 --balance 10000 \
        --strategies rsi,macd,bollinger
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from backend.backtest.data_loader import load_from_binance, load_from_csv, save_to_csv
from backend.backtest.engine import BacktestEngine
from backend.backtest.exchange import BacktestExchange
from backend.backtest.report import generate_report
from backend.config import load_settings
from backend.core.logger import setup_logging
from backend.strategies import STRATEGY_REGISTRY


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a backtest on historical data")
    parser.add_argument(
        "--symbol", default="BTC/USDT", help="Trading pair (default: BTC/USDT)",
    )
    parser.add_argument(
        "--timeframe", default="1h", help="Candle timeframe (default: 1h)",
    )
    parser.add_argument(
        "--start", required=True, help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", required=True, help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--balance", type=float, default=10000.0,
        help="Initial USDT balance (default: 10000)",
    )
    parser.add_argument(
        "--strategies", default="rsi,macd,bollinger",
        help="Comma-separated strategy names (default: rsi,macd,bollinger)",
    )
    parser.add_argument(
        "--csv", default=None,
        help="Path to CSV file with OHLCV data (skips Binance download)",
    )
    parser.add_argument(
        "--save-csv", default=None,
        help="Save downloaded data to this CSV path for future use",
    )
    return parser.parse_args(argv)


async def run_backtest(args: argparse.Namespace) -> None:
    setup_logging(level="INFO", fmt="console")
    settings = load_settings()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(
        tzinfo=UTC
    )
    end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(
        tzinfo=UTC
    )

    if args.csv:
        print(f"Loading data from CSV: {args.csv}")
        ohlcv = load_from_csv(args.csv)
    else:
        print(f"Downloading {args.symbol} {args.timeframe} data from Binance...")
        print(f"  Period: {args.start} to {args.end}")
        ohlcv = await load_from_binance(
            args.symbol, args.timeframe, start_dt, end_dt,
        )

    if args.save_csv:
        save_to_csv(ohlcv, args.save_csv)

    print(f"Loaded {len(ohlcv)} candles")

    if ohlcv.empty:
        print("No data loaded. Exiting.")
        return

    exchange = BacktestExchange(
        ohlcv=ohlcv,
        initial_balance_usdt=args.balance,
        symbol=args.symbol,
    )

    strategy_names = [s.strip() for s in args.strategies.split(",")]
    strategies = []
    config_map = {
        "rsi": settings.strategies.rsi,
        "macd": settings.strategies.macd,
        "bollinger": settings.strategies.bollinger,
    }
    for name in strategy_names:
        cls = STRATEGY_REGISTRY.get(name)
        if cls is None:
            print(f"Warning: unknown strategy '{name}', skipping")
            continue
        config = config_map.get(name)
        strategies.append(cls(config) if config else cls())

    if not strategies:
        print("No valid strategies. Exiting.")
        return

    print(f"Running backtest with strategies: {[s.name for s in strategies]}")
    print()

    engine = BacktestEngine(
        exchange=exchange,
        strategies=strategies,
        symbol=args.symbol,
        risk_config=settings.risk,
    )

    result = await engine.run()
    report = generate_report(result)
    report.print_report()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run_backtest(args))
    except KeyboardInterrupt:
        print("\nBacktest interrupted.")


if __name__ == "__main__":
    sys.exit(main())
