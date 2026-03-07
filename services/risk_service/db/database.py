import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models import (
    Base,
    Assessment,
    RiskPrediction,
    XaiExplanation,
    WeeklyRelapseCheckin,
    Placeholder,
    User,
    UserCredentials,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("risk_db_init")

DATABASE_URL = "postgresql+asyncpg://postgres:piumi1234@localhost:5432/recoverly_platform"

engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS risk"))
            logger.info("Schemas verified")

            await conn.run_sync(Base.metadata.create_all)
            logger.info("Tables created successfully")

    except Exception as e:
        logger.exception(f"Database initialization failed: {e}")
        raise


async def close_db():
    await engine.dispose()
    logger.info("Engine disposed")


async def main():
    await init_db()
    await close_db()


if __name__ == "__main__":
    asyncio.run(main())