"""
Shared pytest fixtures for the Aion backend test suite.

Provides an in-memory SQLite async session factory so that tests that would
normally require a running PostgreSQL database can run in isolation without
any external services.

PostgreSQL-specific type overrides applied **globally at import time**:
  - JSONB  → rendered as JSON  (TEXT-backed in SQLite)
  - UUID   → rendered as VARCHAR (SQLite has no native UUID type)

Note: The JSONB patch (``SQLiteTypeCompiler.visit_JSONB``) is a module-level
monkey-patch that takes effect for every test in the suite.  If you observe
unexpected DDL compilation errors while debugging, check that this module has
been imported (i.e., pytest collected at least one test from this directory).
"""

import pytest
import pytest_asyncio

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Patch PostgreSQL-specific types so SQLAlchemy can compile them for SQLite.
# JSONB → stored as TEXT-backed JSON (SQLite has no binary JSON type).
# ---------------------------------------------------------------------------
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]


@pytest_asyncio.fixture
async def test_engine():
    """
    Async SQLite engine for one test function.
    All tables from the application's declarative metadata are created before
    the test and dropped afterwards.
    """
    # Import all models so they register with the shared Base metadata.
    import app.models.block          # noqa: F401
    import app.models.conversation   # noqa: F401
    import app.models.device         # noqa: F401
    import app.models.plan           # noqa: F401
    import app.models.trigger        # noqa: F401
    import app.models.user           # noqa: F401
    import app.models.system_settings  # noqa: F401

    from app.db.base import Base

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    """
    Provide a fresh AsyncSession for each test, rolling back all changes
    after the test completes so tests remain isolated.
    """
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()
