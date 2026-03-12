"""
Database session management for async SQLAlchemy.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

import logging
from sqlalchemy import exc

logger = logging.getLogger(__name__)

# Create async engine
try:
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
except Exception as e:
    logger.error(f"Failed to create DB engine: {e}")
    engine = None

# Session factory
if engine:
    async_session_maker = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
else:
    async_session_maker = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    if not async_session_maker:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Database connection unavailable. Please check Docker status."
        )

    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
