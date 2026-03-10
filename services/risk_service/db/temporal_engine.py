import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from core.config import DATABASE_URL
from db import Base

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -----------------------------------------------------------------------------
# Engine
# -----------------------------------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=False,          # set True only if you want SQL logs
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
        yield session

# -----------------------------------------------------------------------------
# Create Schema + Tables
# -----------------------------------------------------------------------------
async def init_db():
    async with engine.begin() as conn:
        # Ensure schemas exist (risk + core because auth tables are in core)
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS risk"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        logger.info("✓ Schemas ready (risk, core)")

        # Create all tables from ORM models
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✓ All tables created")

async def close_db():
    await engine.dispose()
    logger.info("✓ Database engine closed")

# -----------------------------------------------------------------------------
# Allow running this file directly to create tables
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(init_db())