from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ml.predictor import predict_arrs
from db.temporal_engine import get_db
from db.models import User, RecommendationAssessment, Recommendation
from shared.auth.dependencies import get_current_user_id
from engine.recommendation_engine import generate_recommendation, submit_feedback
from api.schemas import (
    RecommendRequest,
    RecommendResponse,
    FeedbackRequest,
    FeedbackResponse,
    RecommendationHistoryItem,
    ARRSAnalyzeRequest,
    ARRSAnalyzeResponse,
)

from db.models import ARRSSession
from api.schemas import ARRSSaveSessionRequest, ARRSSaveSessionResponse
from sqlalchemy.ext.asyncio import AsyncSession
from db.temporal_engine import get_db

public_router = APIRouter(
    prefix="/reco",
    tags=["Recommendation"],
)

router = APIRouter(
    prefix="/reco",
    tags=["Recommendation"],
    dependencies=[Depends(get_current_user_id)],
)


@public_router.post("/arrs/analyze", response_model=ARRSAnalyzeResponse)
def analyze_arrs(payload: ARRSAnalyzeRequest):
    try:
        print("ARRS payload received:", payload.model_dump())

        result = predict_arrs(
            answers=payload.answers,
            risk_level=payload.risk_level or "Moderate",
        )

        print("ARRS prediction result:", result)
        return result
    except Exception as e:
        print("ARRS prediction failed:", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"ARRS prediction failed: {str(e)}",
        ) from e


@router.post("/recommend", response_model=RecommendResponse, status_code=status.HTTP_201_CREATED)
async def recommend(
    body: RecommendRequest,
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    user = await db.get(User, logged_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        result = await generate_recommendation(
            db=db,
            user_id=logged_user_id,
            payload=body.questionnaire.payload_dict(),
        )
        await db.commit()
        return RecommendResponse(**result)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendation: {e}",
        ) from e


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    q = (
        select(Recommendation)
        .join(
            RecommendationAssessment,
            RecommendationAssessment.assessment_id == Recommendation.assessment_id,
        )
        .where(
            Recommendation.recommendation_id == body.recommendation_id,
            RecommendationAssessment.user_id == logged_user_id,
        )
        .limit(1)
    )
    recommendation = (await db.execute(q)).scalar_one_or_none()

    if not recommendation:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    try:
        result = await submit_feedback(
            db=db,
            recommendation_id=body.recommendation_id,
            helpful=body.helpful,
            rating=body.rating,
            feedback_action=body.feedback_action,
        )
        await db.commit()
        return FeedbackResponse(**result)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save feedback: {e}",
        ) from e


@router.get("/latest", response_model=RecommendResponse)
async def latest_recommendation(
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    q = (
        select(Recommendation)
        .join(
            RecommendationAssessment,
            RecommendationAssessment.assessment_id == Recommendation.assessment_id,
        )
        .where(RecommendationAssessment.user_id == logged_user_id)
        .order_by(desc(Recommendation.created_at), desc(Recommendation.recommendation_id))
        .limit(1)
    )

    recommendation = (await db.execute(q)).scalar_one_or_none()
    if not recommendation:
        raise HTTPException(status_code=404, detail="No recommendation found")

    assessment = await db.get(RecommendationAssessment, recommendation.assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    return RecommendResponse(
        assessment_id=assessment.assessment_id,
        recommendation_id=recommendation.recommendation_id,
        user_id=assessment.user_id,
        recommendation_family=recommendation.recommendation_family,
        selected_action=recommendation.selected_action,
        classifier_family=recommendation.classifier_family,
        classifier_confidence=float(recommendation.classifier_confidence or 0.0),
        bandit_action=recommendation.bandit_action,
        policy_mode=recommendation.policy_mode,
        policy_version=recommendation.policy_version,
        confidence=float(recommendation.confidence),
        created_at=recommendation.created_at,
        explanation=(recommendation.decision_meta or {}).get("explanation"),
    )

@public_router.post("/arrs/save-session", response_model=ARRSSaveSessionResponse)
async def save_arrs_session(
    payload: ARRSSaveSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        session = ARRSSession(
            user_id="test_user_003",  # replace later with actual logged-in user
            submitted_at=payload.submitted_at,
            risk_level=payload.risk_level,
            predicted_category=payload.predicted_category,
            confidence=payload.confidence,
            answers_json=payload.answers,
            recommendation_json=payload.recommendation,
            feedback_rating=payload.feedback_rating,
            feedback_text=payload.feedback_text,
        )

        db.add(session)
        await db.commit()
        await db.refresh(session)

        return ARRSSaveSessionResponse(
            ok=True,
            session_id=session.session_id,
            message="ARRS session saved successfully."
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save ARRS session: {e}")


@router.get("/history", response_model=list[RecommendationHistoryItem])
async def recommendation_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    q = (
        select(Recommendation)
        .join(
            RecommendationAssessment,
            RecommendationAssessment.assessment_id == Recommendation.assessment_id,
        )
        .options(selectinload(Recommendation.feedback))
        .where(RecommendationAssessment.user_id == logged_user_id)
        .order_by(desc(Recommendation.created_at), desc(Recommendation.recommendation_id))
        .limit(limit)
    )

    rows = (await db.execute(q)).scalars().all()

    out: list[RecommendationHistoryItem] = []
    for row in rows:
        fb = row.feedback
        out.append(
            RecommendationHistoryItem(
                recommendation_id=row.recommendation_id,
                recommendation_family=row.recommendation_family,
                selected_action=row.selected_action,
                classifier_family=row.classifier_family,
                policy_mode=row.policy_mode,
                confidence=float(row.confidence),
                helpful=int(fb.helpful) if fb and fb.helpful is not None else None,
                rating=int(fb.rating) if fb and fb.rating is not None else None,
                created_at=row.created_at,
            )
        )

    return out