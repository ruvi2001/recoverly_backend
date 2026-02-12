"""
Shared database base classes and utilities
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from shared.core.settings import settings

# SQLAlchemy Base for all models
Base = declarative_base()

# Database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.DB_MIN_CONN,
    max_overflow=settings.DB_MAX_CONN - settings.DB_MIN_CONN,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Dependency function to get database session
    Use in FastAPI endpoints like:
    
    @app.get("/users")
    def get_users(db: Session = Depends(get_db)):
        ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
