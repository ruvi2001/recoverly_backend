# services/risk_service/api/routes.py

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, desc, func, cast, Date, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from db.temporal_engine import get_db
from db.models import (
    Patient,
    Assessment,
    RiskPrediction,
    WeeklyRelapseCheckin
)

from shared.auth.dependencies import get_current_user_id
from engine.risk_engine import run_assessment
from engine.monitoring_engine import LOW_MAX, MOD_MAX, HIGH_MAX
from api.schemas import (
    AssessmentInput,
    AssessmentResult,
    PatientCreate,
    PatientResponse,
)

from ml.risk_analyzer import init_analyzer


# ============================================================
# Helpers
# ============================================================
def utcnow_naive() -> datetime:
    return datetime.utcnow()


def utcnow_aware() -> datetime:
    return datetime.now(timezone.utc)


def pg_week_start_date(expr) -> "Date":
    return cast(func.date_trunc("week", expr), Date)


# ============================================================
# FastAPI app
# ============================================================
app = FastAPI(title="Recoverly Risk Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    init_analyzer()

# ============================================================
# RISK ROUTES
# ============================================================
router = APIRouter(
    prefix="/risk",
    tags=["Risk"],
    dependencies=[Depends(get_current_user_id)],
)


def _risk_category(rp: float) -> str:
    if rp >= float(HIGH_MAX):
        return "VERY HIGH RISK"
    if rp >= float(MOD_MAX):
        return "HIGH RISK"
    if rp >= float(LOW_MAX):
        return "MODERATE RISK"
    return "LOW RISK"


def _risk_emoji(rp: float) -> str:
    if rp >= float(HIGH_MAX):
        return "🔴"
    if rp >= float(MOD_MAX):
        return "🟠"
    if rp >= float(LOW_MAX):
        return "🟡"
    return "🟢"


@router.post("/patients", response_model=PatientResponse, status_code=201)
async def create_patient(body: PatientCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(Patient, body.patient_id):
        raise HTTPException(status_code=409, detail="Patient already exists")

    p = Patient(**body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@router.post("/assess", response_model=AssessmentResult, status_code=201)
async def assess(body: AssessmentInput, db: AsyncSession = Depends(get_db)):
    if not await db.get(Patient, body.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    result = await run_assessment(
        db,
        body.patient_id,
        body.assessment_date,
        body.features_dict(),
    )

    await db.commit()
    return AssessmentResult(**result)


# -------------------------
# DAILY TRENDS
# -------------------------
class TrendPoint(BaseModel):
    date: str
    risk_percent: float
    category: str
    emoji: str


@router.get("/trends/{patient_id}", response_model=List[TrendPoint])
async def get_trends(patient_id: str, db: AsyncSession = Depends(get_db)):
    q = (
        select(Assessment, RiskPrediction)
        .join(RiskPrediction, RiskPrediction.assessment_id == Assessment.assessment_id)
        .where(Assessment.patient_id == patient_id)
        .order_by(desc(Assessment.assessment_date), desc(Assessment.assessment_id))
        .limit(60)
    )

    rows = (await db.execute(q)).all()

    points: List[TrendPoint] = []
    for a, rp in reversed(rows):
        risk_percent = float(rp.predicted_risk_percent)
        points.append(
            TrendPoint(
                date=str(a.assessment_date),
                risk_percent=risk_percent,
                category=_risk_category(risk_percent),
                emoji=_risk_emoji(risk_percent),
            )
        )
    return points


# -------------------------
# WEEKLY TRENDS
# -------------------------
class WeeklyTrendPoint(BaseModel):
    week_start: str
    week_label: str
    avg_risk_percent: float
    relapse_reported: bool


@router.get("/weekly-trends/{patient_id}", response_model=List[WeeklyTrendPoint])
async def get_weekly_trends(patient_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    relapse_week = pg_week_start_date(WeeklyRelapseCheckin.reported_at)

    relapse_sq = (
        select(
            relapse_week.label("week_start"),
            (func.max(cast(WeeklyRelapseCheckin.actual_relapse, Integer)) == 1).label("relapse_reported"),
        )
        .where(WeeklyRelapseCheckin.patient_id == patient_id)
        .group_by(relapse_week)
        .subquery()
    )

    assess_week = pg_week_start_date(cast(Assessment.assessment_date, Date))

    q = (
        select(
            assess_week.label("week_start"),
            func.avg(RiskPrediction.predicted_risk_percent).label("avg_risk_percent"),
            func.coalesce(relapse_sq.c.relapse_reported, False).label("relapse_reported"),
            func.to_char(assess_week, "Mon DD").label("week_label"),
        )
        .join(RiskPrediction, RiskPrediction.assessment_id == Assessment.assessment_id)
        .outerjoin(relapse_sq, relapse_sq.c.week_start == assess_week)
        .where(Assessment.patient_id == patient_id)
        .group_by(assess_week, relapse_sq.c.relapse_reported)
        .order_by(desc(assess_week))
        .limit(20)
    )

    rows = (await db.execute(q)).all()

    out: List[WeeklyTrendPoint] = []
    for week_start, avg_risk, relapse_reported, week_label in reversed(rows):
        out.append(
            WeeklyTrendPoint(
                week_start=str(week_start),
                week_label=str(week_label),
                avg_risk_percent=float(avg_risk) if avg_risk is not None else 0.0,
                relapse_reported=bool(relapse_reported),
            )
        )
    return out


# ============================================================
# POPUP RULE
# ============================================================
@router.get("/should-show-popup/{patient_id}")
async def should_show_risk_popup(patient_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    n_assess = (
        await db.execute(
            select(func.count(Assessment.assessment_id)).where(Assessment.patient_id == patient_id)
        )
    ).scalar_one()

    if int(n_assess) < 2:
        return {"should_show": False, "reason": "need_previous_assessment"}

    latest = (
        await db.execute(
            select(RiskPrediction.predicted_risk_percent)
            .join(Assessment, RiskPrediction.assessment_id == Assessment.assessment_id)
            .where(Assessment.patient_id == patient_id)
            .order_by(desc(Assessment.assessment_date), desc(Assessment.assessment_id))
            .limit(1)
        )
    ).scalar_one_or_none()

    if latest is None:
        return {"should_show": False, "reason": "no_prediction"}

    risk_percent = float(latest)
    if risk_percent < float(MOD_MAX):
        return {"should_show": False, "reason": "below_threshold"}

    this_week = cast(func.date_trunc("week", func.now()), Date)

    already = (
        await db.execute(
            select(func.count(WeeklyRelapseCheckin.checkin_id)).where(
                WeeklyRelapseCheckin.patient_id == patient_id,
                WeeklyRelapseCheckin.week_start == this_week,
            )
        )
    ).scalar_one()

    if int(already) > 0:
        return {"should_show": False, "reason": "already_asked_this_week"}

    return {
        "should_show": True,
        "week_start": str(this_week),
        "risk_percent": risk_percent,
        "category": _risk_category(risk_percent),
        "emoji": _risk_emoji(risk_percent),
    }


@router.get("/should-show-weekly-relapse-popup/{patient_id}")
async def should_show_weekly_relapse_popup(patient_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(Patient, patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    this_week = cast(func.date_trunc("week", func.now()), Date)

    already = (
        await db.execute(
            select(func.count(WeeklyRelapseCheckin.checkin_id)).where(
                WeeklyRelapseCheckin.patient_id == patient_id,
                WeeklyRelapseCheckin.week_start == this_week,
            )
        )
    ).scalar_one()

    return {"should_show": int(already) == 0, "week_start": str(this_week)}


class RelapseReportIn(BaseModel):
    patient_id: str
    relapsed: int  # 0 or 1


@router.post("/relapse-report")
async def relapse_report(body: RelapseReportIn, db: AsyncSession = Depends(get_db)):
    if not await db.get(Patient, body.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    v = 1 if int(body.relapsed) == 1 else 0
    this_week = cast(func.date_trunc("week", func.now()), Date)
    now = utcnow_aware()

    existing = (
        await db.execute(
            select(WeeklyRelapseCheckin)
            .where(
                WeeklyRelapseCheckin.patient_id == body.patient_id,
                WeeklyRelapseCheckin.week_start == this_week,
            )
            .order_by(desc(WeeklyRelapseCheckin.checkin_id))
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        existing.actual_relapse = v
        existing.reported_at = now
        existing.week_start = this_week
    else:
        db.add(
            WeeklyRelapseCheckin(
                patient_id=body.patient_id,
                actual_relapse=v,
                reported_at=now,
                week_start=this_week,
            )
        )

    await db.commit()
    return {
        "ok": True,
        "patient_id": body.patient_id,
        "relapsed": bool(v),
        "week_start": str(this_week),
    }



app.include_router(router)