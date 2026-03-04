import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from app.core.config import DATABASE_URL
from app.db import Base

# ✅ IMPORTANT: import only the models you want registered in Base.metadata
# (This prevents SQLAlchemy from trying to map RelapseFollowup)
from app.db.models import (  # noqa: F401
    Patient,
    Assessment,
    RiskPrediction,
    XaiExplanation,
    WeeklyRelapseCheckin,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Engine
# -----------------------------------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # set False in production
    pool_pre_ping=True,
)

# -----------------------------------------------------------------------------
# Session Factory
# -----------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# -----------------------------------------------------------------------------
# Dependency (for FastAPI routes)
# -----------------------------------------------------------------------------
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

# -----------------------------------------------------------------------------
# Create Schema + Tables
# -----------------------------------------------------------------------------
async def init_db():
    async with engine.begin() as conn:
        # Ensure schema exists
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS risk"))
        logger.info("✓ Schema 'risk' ready")

        # Create only the tables for imported models
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Risk tables created")

# -----------------------------------------------------------------------------
# Close engine
# -----------------------------------------------------------------------------
async def close_db():
    await engine.dispose()
    logger.info("✓ Database engine closed")

# -----------------------------------------------------------------------------
# Allow running this file directly to create tables
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(init_db())