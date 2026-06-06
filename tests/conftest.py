"""Pytest configuration and shared fixtures.

Sets ``SPENDIT_DB_PATH`` to a temporary file *before* the app is imported, so
the production engine is wired against an isolated database that is rebuilt
between tests. Static analysis: this file MUST set the env var before any
``app.*`` import runs (test modules are collected after conftest).
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Point the app at a throwaway SQLite file before importing any app module.
_TMP_DIR = Path(tempfile.mkdtemp(prefix="spendit-tests-"))
os.environ["SPENDIT_DB_PATH"] = str(_TMP_DIR / "spendit.test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema() -> Iterator[None]:
    """Recreate tables before each test for full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Iterator:
    """Yields a SQLAlchemy session bound to the test engine."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI TestClient with lifespan disabled (schema handled by fixture)."""
    with TestClient(app) as c:
        yield c
