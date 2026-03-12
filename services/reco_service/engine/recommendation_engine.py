import logging
from typing import Any
import json
import random
from pathlib import Path

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import (
    RecommendationAssessment,
    Recommendation,
    RecommendationFeedback,
    RiskAssessment,
    RiskPrediction,
)
from ml.encoder import get_encoder
from ml.policy import get_policy
from ml.bandit import get_bandit_runtime

logger = logging.getLogger(__name__)

LIBRARY_PATH = Path(__file__).resolve().parents[1] / "ml" / "artifacts" / "recommendation_library.json"

with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
    RECOMMENDATION_LIBRARY = json.load(f)

def compute_feedback_reward(
    helpful: int,
    rating: int,
    feedback_action: str | None = None,
) -> float:
    """
    Convert user feedback into a reward in [0, 1].

    Base design:
    - helpful: strongest signal
    - rating: supporting signal
    - feedback_action: optional behavioral signal
    """

    action_weight = {
        "ignored": 0.0,
        "viewed": 0.20,
        "tried": 0.60,
        "completed": 1.00,
    }

    helpful_score = 1.0 if int(helpful) == 1 else 0.0
    rating_score = max(1, min(5, int(rating))) / 5.0

    behavioral_score = None
    if feedback_action:
        behavioral_score = action_weight.get(feedback_action.strip().lower())

    if behavioral_score is None:
        reward = (0.70 * helpful_score) + (0.30 * rating_score)
    else:
        reward = (
            (0.60 * helpful_score)
            + (0.25 * rating_score)
            + (0.15 * behavioral_score)
        )

    return float(round(max(0.0, min(1.0, reward)), 4))

def _pick_recommendation(selected_action: str) -> dict[str, str]:
    options = RECOMMENDATION_LIBRARY.get(selected_action, [])

    if not options:
        return {
            "id": "fallback_001",
            "title": "Take a short pause",
            "message": "Pause for a moment and focus on one small positive step you can take right now.",
        }

    return random.choice(options)

async def generate_recommendation(
    db: AsyncSession,
    user_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Full ARRS flow:
    1. fetch latest risk level from risk_service outputs
    2. inject risk level into ARRS payload
    3. encode payload into model features
    4. run classifier + hybrid policy
    5. save assessment snapshot
    6. save recommendation
    """

    latest_risk_q = (
        select(RiskPrediction.risk_level)
        .join(
            RiskAssessment,
            RiskAssessment.assessment_id == RiskPrediction.assessment_id,
        )
        .where(RiskAssessment.user_id == user_id)
        .order_by(
            desc(RiskAssessment.assessed_at),
            desc(RiskAssessment.assessment_id),
        )
        .limit(1)
    )

    latest_risk_level = (await db.execute(latest_risk_q)).scalar_one_or_none()
    if not latest_risk_level:
        raise ValueError("No risk level found for user. Complete risk assessment first.")

    full_payload = {
        **payload,
        "relapse_risk_level": str(latest_risk_level).strip().upper(),
    }

    encoder = get_encoder()
    encoded = encoder.encode(full_payload)

    assessment = RecommendationAssessment(
        user_id=user_id,
        relapse_risk_level=str(latest_risk_level).strip().upper(),
        raw_payload=full_payload,
        encoded_vector=encoded,
        request_meta={
            "feature_count": len(encoded),
        },
    )
    db.add(assessment)
    await db.flush()

    policy = get_policy()
    bandit = get_bandit_runtime()

    rewarded_events_count = await _count_rewarded_events(db=db, user_id=user_id)

    feature_vector = encoder.vector(encoded)

    decision = policy.decide(
        encoded_features=encoded,
        feature_vector=feature_vector,
        bandit_runtime=bandit,
        rewarded_events_count=rewarded_events_count,
    )

    
    selected_action = decision["selected_action"]
    recommendation_item = _pick_recommendation(selected_action)

    decision_meta = decision.get("decision_meta", {}) or {}
    decision_meta["recommendation_item"] = recommendation_item

    recommendation = Recommendation(
        assessment_id=assessment.assessment_id,
        recommendation_family=decision["recommendation_family"],
        selected_action=selected_action,
        classifier_family=decision["classifier_family"],
        classifier_confidence=decision["classifier_confidence"],
        bandit_action=decision.get("bandit_action"),
        policy_mode=decision["policy_mode"],
        policy_version=decision.get("policy_version"),
        confidence=decision["confidence"],
        decision_meta=decision_meta,
    )
    db.add(recommendation)
    await db.flush()

    return {
        "assessment_id": assessment.assessment_id,
        "recommendation_id": recommendation.recommendation_id,
        "user_id": user_id,
        "recommendation_family": recommendation.recommendation_family,
        "selected_action": recommendation.selected_action,
        "classifier_family": recommendation.classifier_family,
        "classifier_confidence": float(recommendation.classifier_confidence or 0.0),
        "bandit_action": recommendation.bandit_action,
        "policy_mode": recommendation.policy_mode,
        "policy_version": recommendation.policy_version,
        "confidence": float(recommendation.confidence),
        "created_at": recommendation.created_at,
        "explanation": (recommendation.decision_meta or {}).get("explanation"),
        "recommendation_title": recommendation_item["title"],
        "recommendation_message": recommendation_item["message"],
    }


async def submit_feedback(
    db: AsyncSession,
    recommendation_id: int,
    helpful: int,
    rating: int,
    feedback_action: str | None = None,
) -> dict[str, Any]:
    """
    Save feedback and update bandit runtime.
    """

    q = (
        select(Recommendation)
        .options(selectinload(Recommendation.assessment), selectinload(Recommendation.feedback))
        .where(Recommendation.recommendation_id == recommendation_id)
        .limit(1)
    )
    recommendation = (await db.execute(q)).scalar_one_or_none()

    if recommendation is None:
        raise ValueError("Recommendation not found.")

    existing_feedback = recommendation.feedback

    if existing_feedback:
        existing_feedback.helpful = int(helpful)
        existing_feedback.rating = int(rating)
        existing_feedback.feedback_action = feedback_action
        feedback_row = existing_feedback
    else:
        feedback_row = RecommendationFeedback(
            recommendation_id=recommendation.recommendation_id,
            helpful=int(helpful),
            rating=int(rating),
            feedback_action=feedback_action,
            feedback_meta={},
        )
        db.add(feedback_row)
        await db.flush()

    reward = compute_feedback_reward(
        helpful=int(helpful),
        rating=int(rating),
        feedback_action=feedback_action,
    )

    recommendation.reward = reward

    bandit = get_bandit_runtime()
    encoded_features = recommendation.assessment.encoded_vector if recommendation.assessment else None

    bandit_updated = False
    if encoded_features:
        bandit.update_from_feedback(
            action=recommendation.selected_action,
            encoded_features=encoded_features,
            reward=reward,
        )
        bandit.save()
        bandit_updated = True

    return {
        "ok": True,
        "recommendation_id": recommendation.recommendation_id,
        "helpful": int(helpful),
        "rating": int(rating),
        "bandit_updated": bandit_updated,
    }


async def _count_rewarded_events(db: AsyncSession, user_id: str) -> int:
    q = (
        select(RecommendationFeedback.feedback_id)
        .join(
            Recommendation,
            Recommendation.recommendation_id == RecommendationFeedback.recommendation_id,
        )
        .join(
            RecommendationAssessment,
            RecommendationAssessment.assessment_id == Recommendation.assessment_id,
        )
        .where(
            RecommendationAssessment.user_id == user_id,
            Recommendation.reward.is_not(None),
        )
    )

    rows = (await db.execute(q)).scalars().all()
    return len(rows)