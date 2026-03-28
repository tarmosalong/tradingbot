from __future__ import annotations

import asyncio
import signal
import sys

from backend.config import load_settings
from backend.core.engine import TradingEngine
from backend.core.logger import get_logger, setup_logging
from backend.database import Database
from backend.exchange import create_exchange
from backend.strategies import STRATEGY_REGISTRY

logger = get_logger("main")


def _build_strategies(settings):
    """Instantiate enabled strategies from the registry."""
    strategies = []
    for name in settings.strategies.enabled:
        cls = STRATEGY_REGISTRY.get(name)
        if cls is None:
            logger.warning("Unknown strategy, skipping", name=name)
            continue
        config_map = {
            "rsi": settings.strategies.rsi,
            "macd": settings.strategies.macd,
            "bollinger": settings.strategies.bollinger,
        }
        config = config_map.get(name)
        strategies.append(cls(config) if config else cls())
    return strategies


async def run() -> None:
    settings = load_settings()
    setup_logging(level=settings.log_level, fmt="console")

    logger.info(
        "Starting trading bot",
        mode=settings.trading.mode,
        pairs=settings.trading.pairs,
    )

    db = Database()
    await db.connect()

    exchange = create_exchange(settings)
    strategies = _build_strategies(settings)

    engine = TradingEngine(
        settings=settings,
        exchange=exchange,
        database=db,
        strategies=strategies,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(engine.stop()))

    try:
        await engine.start()
    finally:
        await exchange.close()
        await db.close()
        logger.info("Shutdown complete")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
