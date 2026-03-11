from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import Base


# --------------------------
# RECO schema
# --------------------------
class RecommendationAssessment(Base):
    __tablename__ = "assessments"
    __table_args__ = {"schema": "reco"}

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        String(255),
        ForeignKey("core.users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relapse_risk_level = Column(String(50), nullable=False)
    raw_payload = Column(JSONB, nullable=False)
    encoded_vector = Column(JSONB, nullable=True)
    request_meta = Column(JSONB, nullable=True)

    assessed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    user = relationship("User")

    recommendation = relationship(
        "Recommendation",
        back_populates="assessment",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0.00 AND 1.00", name="ck_reco_confidence"),
        CheckConstraint(
            "classifier_confidence IS NULL OR classifier_confidence BETWEEN 0.00 AND 1.00",
            name="ck_reco_classifier_confidence",
        ),
        CheckConstraint(
            "reward IS NULL OR reward BETWEEN 0.00 AND 1.00",
            name="ck_reco_reward",
        ),
        {"schema": "reco"},
    )

    recommendation_id = Column(Integer, primary_key=True, autoincrement=True)

    assessment_id = Column(
        Integer,
        ForeignKey("reco.assessments.assessment_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    recommendation_family = Column(String(100), nullable=False)
    selected_action = Column(String(150), nullable=False)

    classifier_family = Column(String(100), nullable=False)
    classifier_confidence = Column(Numeric(8, 6), nullable=True)

    bandit_action = Column(String(150), nullable=True)
    policy_mode = Column(String(50), nullable=False)
    policy_version = Column(String(100), nullable=True)

    confidence = Column(Numeric(8, 6), nullable=False)
    reward = Column(Numeric(8, 6), nullable=True)

    decision_meta = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    assessment = relationship("RecommendationAssessment", back_populates="recommendation")

    feedback = relationship(
        "RecommendationFeedback",
        back_populates="recommendation",
        uselist=False,
        cascade="all, delete-orphan",
    )


class RecommendationFeedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_reco_feedback_recommendation"),
        CheckConstraint("helpful IN (0, 1)", name="ck_reco_feedback_helpful"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_reco_feedback_rating"),
        {"schema": "reco"},
    )

    feedback_id = Column(Integer, primary_key=True, autoincrement=True)

    recommendation_id = Column(
        Integer,
        ForeignKey("reco.recommendations.recommendation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    helpful = Column(SmallInteger, nullable=False)
    rating = Column(SmallInteger, nullable=False)
    feedback_action = Column(String(150), nullable=True)

    feedback_meta = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    recommendation = relationship("Recommendation", back_populates="feedback")


class Placeholder(Base):
    __tablename__ = "placeholder"
    __table_args__ = {"schema": "reco"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    note = Column(Text, nullable=True)


# --------------------------
# RISK schema (read-only in reco_service)
# Used to fetch latest risk_level from risk_service outputs
# --------------------------
class RiskAssessment(Base):
    __tablename__ = "assessments"
    __table_args__ = {"schema": "risk"}

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        String(255),
        ForeignKey("core.users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assessment_date = Column(Date, nullable=False, server_default=func.current_date())
    assessed_at = Column(DateTime, nullable=False, server_default=func.now())


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (
        CheckConstraint("predicted_label IN (0, 1)", name="ck_risk_predicted_label"),
        CheckConstraint(
            "predicted_risk_percent BETWEEN 0.00 AND 100.00",
            name="ck_risk_predicted_percent",
        ),
        {"schema": "risk"},
    )

    prediction_id = Column(Integer, primary_key=True, autoincrement=True)

    assessment_id = Column(
        Integer,
        ForeignKey("risk.assessments.assessment_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    predicted_label = Column(SmallInteger, nullable=False)
    predicted_risk_percent = Column(Numeric(5, 2), nullable=False)
    risk_level = Column(String(20), nullable=False)
    model_version = Column(String(100), nullable=False)
    predicted_at = Column(DateTime, nullable=False, server_default=func.now())


# --------------------------
# CORE schema (auth)
# --------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    user_id = Column(String(255), primary_key=True)
    username = Column(String(100), unique=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    last_active = Column(DateTime, nullable=True)
    status = Column(String(50), server_default="active", nullable=True)

    meta = Column("metadata", JSONB, nullable=True)

    credentials = relationship(
        "UserCredentials",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserCredentials(Base):
    __tablename__ = "user_credentials"
    __table_args__ = {"schema": "core"}

    user_id = Column(
        String(255),
        ForeignKey("core.users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )

    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)
    last_login = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="credentials")