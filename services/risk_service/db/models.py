from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UniqueConstraint, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base

# --------------------------
# RISK schema
# --------------------------
class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint("age > 0 AND age < 130", name="ck_patient_age"),
        CheckConstraint("days_since_last_use >= 0", name="ck_patient_days"),
        {"schema": "risk"},
    )

    patient_id = Column(String(255), primary_key=True)
    age = Column(Integer, nullable=False)
    days_since_last_use = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    assessments = relationship(
        "Assessment",
        back_populates="patient",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("self_efficacy_doubt BETWEEN 1 AND 7", name="ck_self_efficacy_doubt"),
        CheckConstraint("emotional_distress BETWEEN 1 AND 7", name="ck_emotional_distress"),
        CheckConstraint("anger_irritability BETWEEN 1 AND 7", name="ck_anger_irritability"),
        CheckConstraint("unclear_thinking BETWEEN 1 AND 7", name="ck_unclear_thinking"),
        CheckConstraint("poor_concentration BETWEEN 1 AND 7", name="ck_poor_concentration"),
        CheckConstraint("feeling_trapped BETWEEN 1 AND 7", name="ck_feeling_trapped"),
        CheckConstraint("sleep_disturbance BETWEEN 1 AND 7", name="ck_sleep_disturbance"),
        CheckConstraint("craving_thoughts BETWEEN 1 AND 7", name="ck_craving_thoughts"),
        CheckConstraint("relapse_ideation BETWEEN 1 AND 7", name="ck_relapse_ideation"),
        CheckConstraint("recovery_actions BETWEEN 1 AND 7", name="ck_recovery_actions"),
        {"schema": "risk"},
    )

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(255), ForeignKey("risk.patients.patient_id", ondelete="CASCADE"), nullable=False)
    assessment_date = Column(Date, nullable=False, server_default=func.current_date())
    assessed_at = Column(DateTime, nullable=False, server_default=func.now())

    self_efficacy_doubt = Column(Integer, nullable=False)
    emotional_distress = Column(Integer, nullable=False)
    anger_irritability = Column(Integer, nullable=False)
    unclear_thinking = Column(Integer, nullable=False)
    poor_concentration = Column(Integer, nullable=False)
    feeling_trapped = Column(Integer, nullable=False)
    sleep_disturbance = Column(Integer, nullable=False)
    craving_thoughts = Column(Integer, nullable=False)
    relapse_ideation = Column(Integer, nullable=False)
    recovery_actions = Column(Integer, nullable=False)

    patient = relationship("Patient", back_populates="assessments")

    prediction = relationship("RiskPrediction", back_populates="assessment", uselist=False, cascade="all, delete-orphan")
   

class RiskPrediction(Base):
    __tablename__ = "risk_predictions"
    __table_args__ = (
        CheckConstraint("predicted_label IN (0, 1)", name="ck_predicted_label"),
        CheckConstraint("predicted_risk_percent BETWEEN 0.00 AND 100.00", name="ck_risk_percent"),
        {"schema": "risk"},
    )

    prediction_id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("risk.assessments.assessment_id", ondelete="CASCADE"),
                           nullable=False, unique=True)
    predicted_label = Column(SmallInteger, nullable=False)
    predicted_risk_percent = Column(Numeric(5, 2), nullable=False)
    model_version = Column(String(50), nullable=False)
    predicted_at = Column(DateTime, nullable=False, server_default=func.now())

    assessment = relationship("Assessment", back_populates="prediction")

    xai_explanations = relationship(
        "XaiExplanation",
        back_populates="prediction",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

class XaiExplanation(Base):
    __tablename__ = "xai_explanations"
    __table_args__ = (
        UniqueConstraint("prediction_id", "feature_name", name="uq_xai_prediction_feature"),
        UniqueConstraint("prediction_id", "rank", name="uq_xai_prediction_rank"),
        CheckConstraint("feature_value BETWEEN 1 AND 7", name="ck_xai_feature_value"),
        CheckConstraint("rank BETWEEN 1 AND 10", name="ck_xai_rank"),
        {"schema": "risk"},
    )

    xai_id = Column(Integer, primary_key=True, autoincrement=True)
    prediction_id = Column(Integer, ForeignKey("risk.risk_predictions.prediction_id", ondelete="CASCADE"),
                           nullable=False)
    feature_name = Column(String(100), nullable=False)
    feature_value = Column(Integer, nullable=False)
    contribution = Column(Numeric(10, 6), nullable=False)
    rank = Column(Integer, nullable=False)

    prediction = relationship("RiskPrediction", back_populates="xai_explanations")


class WeeklyRelapseCheckin(Base):
    __tablename__ = "weekly_relapse_checkins"
    __table_args__ = (CheckConstraint("actual_relapse IN (0, 1)", name="ck_weekly_actual_relapse"), {"schema": "risk"})

    checkin_id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(255), ForeignKey("risk.patients.patient_id", ondelete="CASCADE"),
                        nullable=False, index=True)
    actual_relapse = Column(SmallInteger, nullable=False)
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    patient = relationship("Patient")

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

    user_id = Column(String(255), ForeignKey("core.users.user_id", ondelete="CASCADE"), primary_key=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)
    last_login = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="credentials")