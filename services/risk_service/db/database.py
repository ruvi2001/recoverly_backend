import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# IMPORTANT: use package-relative imports so "python -m ..." works
from . import Base
from .models import (  # noqa: F401
    Patient,
    Assessment,
    RiskPrediction,
    WeeklyRelapseCheckin,
    Placeholder,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("risk_db_init")

# ✅ Hard-coded async DB URL (no .env needed)
DATABASE_URL = "postgresql+asyncpg://postgres:piumi1234@localhost:5432/recoverly_platform"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,          # set False in production
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# FastAPI dependency (if you want to use this in routes later)
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        # Ensure schema exists
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS risk"))
        logger.info("✓ Schema 'risk' ready")

        # Create tables defined in models (won't recreate if they already exist)
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ Tables created / verified")


async def close_db():
    await engine.dispose()
    logger.info("✓ Engine disposed")


if __name__ == "__main__":
    asyncio.run(init_db())