from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ml.predictor import predict_arrs
from db.temporal_engine import get_db
from db.models import (
    User,
    RecommendationAssessment,
    Recommendation,
    RecommendationFeedback,
    ARRSSession,
    RiskAssessment,
    RiskPrediction,
)
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
from api.schemas import ARRSSaveSessionRequest, ARRSSaveSessionResponse

public_router = APIRouter(
    prefix="/reco",
    tags=["Recommendation"],
)

router = APIRouter(
    prefix="/reco",
    tags=["Recommendation"],
    dependencies=[Depends(get_current_user_id)],
)


@router.post("/arrs/analyze", response_model=ARRSAnalyzeResponse)
async def analyze_arrs(
    payload: ARRSAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    try:
        risk_level = await _get_latest_risk_level(
            db=db,
            user_id=logged_user_id,
            fallback=payload.risk_level or "Moderate",
        )

        print("ARRS payload received:", payload.model_dump())
        print("Latest risk level used for ARRS:", risk_level)

        result = predict_arrs(
            answers=payload.answers,
            risk_level=risk_level,
        )

        result["risk_level"] = risk_level

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

async def _get_latest_risk_level(
    db: AsyncSession,
    user_id: str,
    fallback: str = "Moderate",
) -> str:
    q = (
        select(RiskPrediction.risk_level)
        .join(
            RiskAssessment,
            RiskAssessment.assessment_id == RiskPrediction.assessment_id,
        )
        .where(RiskAssessment.user_id == user_id)
        .order_by(desc(RiskPrediction.predicted_at), desc(RiskPrediction.prediction_id))
        .limit(1)
    )

    result = await db.execute(q)
    latest_risk_level = result.scalar_one_or_none()

    return latest_risk_level or fallback

def _extract_selected_action(recommendation_payload):
    if isinstance(recommendation_payload, dict):
        for key in ("selected_action", "action_type", "id", "title"):
            value = recommendation_payload.get(key)
            if value:
                return str(value)[:150]

    if isinstance(recommendation_payload, list) and recommendation_payload:
        first_item = recommendation_payload[0]

        if isinstance(first_item, dict):
            for key in ("selected_action", "action_type", "id", "title"):
                value = first_item.get(key)
                if value:
                    return str(value)[:150]

        return str(first_item)[:150]

    if isinstance(recommendation_payload, str) and recommendation_payload.strip():
        return recommendation_payload.strip()[:150]

    return "ARRS_MOBILE_RECOMMENDATION"

@router.post("/arrs/save-session", response_model=ARRSSaveSessionResponse)
async def save_arrs_session(
    payload: ARRSSaveSessionRequest,
    db: AsyncSession = Depends(get_db),
    logged_user_id: str = Depends(get_current_user_id),
):
    user_id = logged_user_id

    risk_level = await _get_latest_risk_level(
        db=db,
        user_id=user_id,
        fallback=payload.risk_level or "Moderate",
    )
    
    confidence = float(payload.confidence or 0.0)

    if confidence < 0:
        confidence = 0.0
    if confidence > 1:
        confidence = 1.0

    selected_action = _extract_selected_action(payload.recommendation)

    try:
        session = ARRSSession(
            user_id=user_id,
            submitted_at=payload.submitted_at,
            risk_level=risk_level,
            predicted_category=payload.predicted_category,
            confidence=confidence,
            answers_json=payload.answers,
            recommendation_json=payload.recommendation,
            feedback_rating=payload.feedback_rating,
            feedback_text=payload.feedback_text,
        )

        db.add(session)
        await db.flush()

        assessment = RecommendationAssessment(
            user_id=user_id,
            relapse_risk_level=risk_level,
            raw_payload={
                "submitted_at": payload.submitted_at,
                "answers": payload.answers,
                "arrs_session_id": session.session_id,
                "source": "mobile_arrs_flow",
            },
            encoded_vector=None,
            request_meta={
                "arrs_session_id": session.session_id,
                "source": "mobile_app",
            },
        )

        db.add(assessment)
        await db.flush()

        recommendation = Recommendation(
            assessment_id=assessment.assessment_id,
            user_id=user_id,
            recommendation_family=payload.predicted_category,
            selected_action=selected_action,
            classifier_family=payload.predicted_category,
            classifier_confidence=confidence,
            bandit_action=selected_action,
            policy_mode="mobile_arrs_save",
            policy_version="arrs_mobile_v1",
            confidence=confidence,
            decision_meta={
                "arrs_session_id": session.session_id,
                "submitted_at": payload.submitted_at,
                "risk_level": risk_level,
                "recommendation": payload.recommendation,
                "source": "mobile_arrs_save_session",
            },
        )

        db.add(recommendation)
        await db.flush()

        if payload.feedback_rating is not None:
            helpful = (
                int(payload.feedback_helpful)
                if payload.feedback_helpful is not None
                else 1 if payload.feedback_rating >= 3 else 0
            )

            feedback = RecommendationFeedback(
                recommendation_id=recommendation.recommendation_id,
                helpful=helpful,
                rating=payload.feedback_rating,
                feedback_action=(
                    "acted_on"
                    if payload.acted_on is True
                    else "not_acted_on"
                    if payload.acted_on is False
                    else None
                ),
                feedback_meta={
                    "arrs_session_id": session.session_id,
                    "feedback_text": payload.feedback_text,
                    "acted_on": payload.acted_on,
                    "source": "mobile_feedback_screen",
                },
            )

            db.add(feedback)

        await db.commit()
        await db.refresh(session)

        return ARRSSaveSessionResponse(
            ok=True,
            session_id=session.session_id,
            recommendation_id=recommendation.recommendation_id,
            message="ARRS recommendation saved successfully.",
        )

    except Exception as e:
        await db.rollback()

        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save ARRS session: {e}",
        )

@router.get("/arrs/latest")
async def latest_arrs_recommendation(
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
        .limit(1)
    )

    recommendation = (await db.execute(q)).scalar_one_or_none()

    if not recommendation:
        raise HTTPException(status_code=404, detail="No ARRS recommendation found")

    meta = recommendation.decision_meta or {}
    feedback = recommendation.feedback

    return {
        "recommendation_id": recommendation.recommendation_id,
        "assessment_id": recommendation.assessment_id,
        "predicted_category": recommendation.recommendation_family,
        "selected_action": recommendation.selected_action,
        "confidence": float(recommendation.confidence),
        "recommendation": meta.get("recommendation"),
        "risk_level": meta.get("risk_level"),
        "created_at": recommendation.created_at,
        "feedback_given": feedback is not None,
        "feedback_rating": int(feedback.rating) if feedback else None,
    }

@router.post("/arrs/feedback")
async def save_arrs_feedback(
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
        .options(selectinload(Recommendation.feedback))
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
        if recommendation.feedback:
            recommendation.feedback.helpful = body.helpful
            recommendation.feedback.rating = body.rating
            recommendation.feedback.feedback_action = body.feedback_action
            recommendation.feedback.feedback_meta = {
                **(recommendation.feedback.feedback_meta or {}),
                "source": "latest_recommendation_feedback_update",
            }
        else:
            feedback = RecommendationFeedback(
                recommendation_id=recommendation.recommendation_id,
                helpful=body.helpful,
                rating=body.rating,
                feedback_action=body.feedback_action,
                feedback_meta={
                    "source": "latest_recommendation_feedback",
                },
            )
            db.add(feedback)

        await db.commit()

        return {
            "ok": True,
            "recommendation_id": recommendation.recommendation_id,
            "message": "Feedback saved successfully.",
        }

    except Exception as e:
        await db.rollback()

        import traceback
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save ARRS feedback: {e}",
        )

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