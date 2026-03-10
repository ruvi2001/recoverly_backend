from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


# ============================
# MODEL REGISTRY
# ============================

class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = {"schema": "causal"}

    model_id = Column(Integer, primary_key=True, index=True)
    model_name = Column(Text, nullable=False, default="tfidf+calibrated_svc")
    model_version = Column(Text, nullable=False)
    artifacts_path = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text)


# ============================
# INDIVIDUAL PREDICTIONS
# ============================

class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = {"schema": "causal"}

    prediction_id = Column(BigInteger, primary_key=True, index=True)

    user_id = Column(String(255), nullable=True)

    input_text = Column(Text, nullable=False)
    cleaned_text = Column(Text)

    most_impactful = Column(Text, nullable=False)

    top1_label = Column(Text, nullable=False)
    top1_level = Column(String(20), nullable=False)

    top2_label = Column(Text)
    top2_level = Column(String(20))

    top3_label = Column(Text)
    top3_level = Column(String(20))

    model_id = Column(
        Integer,
        ForeignKey("causal.model_registry.model_id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    meta = Column("metadata", JSON)


# ============================
# GROUP SUMMARIES
# ============================

class GroupSummary(Base):
    __tablename__ = "group_summaries"
    __table_args__ = {"schema": "causal"}

    group_id = Column(BigInteger, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    total_analyzed = Column(Integer, nullable=False)
    distribution = Column(JSON, nullable=False)

    model_id = Column(
        Integer,
        ForeignKey("causal.model_registry.model_id", ondelete="SET NULL"),
        nullable=True
    )

    meta = Column("metadata", JSON)


# ============================
# COUNSELLOR AUTH (ONLY)
# ============================

class Counsellor(Base):
    __tablename__ = "counsellors"
    __table_args__ = {"schema": "causal"}

    counsellor_id = Column(String(255), primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=True)

    password_hash = Column(Text, nullable=False)
    role = Column(String(50), nullable=False, default="admin")
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    meta = Column("metadata", JSONB, nullable=False, server_default="{}")