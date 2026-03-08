import logging
from datetime import date
from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import Assessment, RiskPrediction, XaiExplanation
from ml.risk_analyzer import get_analyzer

logger = logging.getLogger(__name__)


async def run_assessment(
    db: AsyncSession,
    user_id: str,
    assessment_date: date,
    features: Dict[str, int],
) -> Dict:
    assessment = Assessment(
        user_id=user_id,
        assessment_date=assessment_date,
        **features,
    )
    db.add(assessment)
    await db.flush()

    result = await get_analyzer().predict(features)

    prediction = RiskPrediction(
        assessment_id=assessment.assessment_id,
        predicted_label=result["predicted_label"],
        predicted_risk_percent=result["predicted_risk_percent"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
    )
    db.add(prediction)
    await db.flush()

    for row in result["xai"]:
        db.add(
            XaiExplanation(
                prediction_id=prediction.prediction_id,
                feature_name=row["feature_name"],
                feature_value=int(row["feature_value"]),
                contribution=float(row["contribution"]),
                rank=int(row["rank"]),
            )
        )

    return {
        "assessment_id": assessment.assessment_id,
        "user_id": user_id,
        "assessment_date": assessment_date,
        "prediction_id": prediction.prediction_id,
        **{
            k: result[k]
            for k in [
                "predicted_label",
                "predicted_risk_percent",
                "risk_level",
                "category",
                "emoji",
                "total_score",
                "model_version",
                "xai",
            ]
        },
    }


async def get_user_history(db: AsyncSession, user_id: str):
    result = await db.execute(
        select(Assessment)
        .where(Assessment.user_id == user_id)
        .options(
            selectinload(Assessment.prediction).selectinload(RiskPrediction.xai_explanations),
        )
        .order_by(Assessment.assessed_at.desc())
    )
    return result.scalars().all()