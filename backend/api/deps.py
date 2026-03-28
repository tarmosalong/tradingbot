from __future__ import annotations

from backend.database import Database

_db: Database | None = None


def set_database(db: Database) -> None:
    global _db
    _db = db


def get_database() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db
