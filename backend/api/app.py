from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.bot_runner import bot_runner
from backend.api.deps import set_database
from backend.api.routes import router
from backend.api.websocket import ws_router
from backend.config import load_settings
from backend.core.logger import get_logger, setup_logging
from backend.database import Database

logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    setup_logging(level=settings.log_level, fmt="console")

    db = Database()
    await db.connect()
    set_database(db)
    logger.info("API started, database connected")

    yield

    await bot_runner.shutdown()
    await db.close()
    set_database(None)
    logger.info("API shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Trading Bot API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")
    app.include_router(ws_router)

    return app
