import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from core.config import DATABASE_URL
from db import Base

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------
# Engine
# ---------------------------------------------------
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

# ---------------------------------------------------
# Session factory
# ---------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ---------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

# ---------------------------------------------------
# Create schemas + tables
# ---------------------------------------------------
async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS reco"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS risk"))

        logger.info("✓ Schemas ready (reco, core, risk)")

        await conn.run_sync(Base.metadata.create_all)

        logger.info("✓ Reco tables created")


async def close_db():
    await engine.dispose()
    logger.info("✓ Database engine closed")


# ---------------------------------------------------
# Run directly to create tables
# ---------------------------------------------------
if __name__ == "__main__":
    asyncio.run(init_db())