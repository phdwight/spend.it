"""Database engine and session configuration."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = Path(os.environ.get("SPENDIT_DB_PATH", "data/spendit.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create tables if they do not already exist."""
    # Import models so they register with Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """Add new columns to existing tables without a full migration tool.

    Keeps upgrades painless for already-deployed SQLite databases.
    """
    inspector = inspect(engine)
    if "expenses" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("expenses")}
    if "photo" not in existing_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN photo TEXT"))
