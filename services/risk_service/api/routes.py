import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, desc, func, cast, Date, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from db.temporal_engine import get_db
from db.models import (
    Assessment,
    RiskPrediction,
    WeeklyRelapseCheckin,
    User,
    UserCredentials,
)

from shared.auth.jwt_utils import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
)

from engine.risk_engine import run_assessment
from engine.monitoring_engine import LOW_MAX, MOD_MAX, HIGH_MAX
from api.schemas import (
    AssessmentInput,
    AssessmentResult,
)

from ml.risk_analyzer import init_analyzer


def utcnow_naive() -> datetime:
    return datetime.utcnow()


def utcnow_aware() -> datetime:
    return datetime.now(timezone.utc)


def pg_week_start_date(expr) -> "Date":
    return cast(func.date_trunc("week", expr), Date)


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


auth_router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str


class MeOut(BaseModel):
    user_id: str
    email: EmailStr
    full_name: Optional[str]
    role: str


def _role_of(u: User) -> str:
    return (u.meta or {}).get("role", "patient")


@auth_router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    email = body.email.lower().strip()

    existing = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    now = utcnow_naive()
    new_user_id = f"user_{uuid.uuid4().hex[:12]}"

    user = User(
        user_id=new_user_id,
        email=email,
        full_name=body.full_name,
        status="active",
        meta={"role": "patient"},
        created_at=now,
        last_active=now,
    )
    db.add(user)
    await db.flush()

    cred = UserCredentials(
        user_id=new_user_id,
        password_hash=hash_password(body.password),
        created_at=now,
        updated_at=now,
    )
    db.add(cred)

    await db.commit()
    await db.refresh(user)

    token = create_access_token(user_id=user.user_id, expires_minutes=60 * 24)

    return AuthResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
        full_name=user.full_name,
        role=_role_of(user),
    )


@auth_router.post("/login", response_model=AuthResponse)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    email = body.email.lower().strip()

    u = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    cred = await db.get(UserCredentials, u.user_id)
    if not cred or not verify_password(body.password, cred.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    now = utcnow_naive()
    cred.last_login = now
    cred.updated_at = now
    await db.commit()

    token = create_access_token(user_id=u.user_id, expires_minutes=60 * 24)

    return AuthResponse(
        token=token,
        user_id=u.user_id,
        email=u.email,
        full_name=u.full_name,
        role=_role_of(u),
    )


async def get_current_patient(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    u = await db.get(User, payload["sub"])
    if not u:
        raise HTTPException(status_code=401, detail="User not found")

    return u


@auth_router.get("/me", response_model=MeOut)
async def me(current: User = Depends(get_current_patient)):
    return MeOut(
        user_id=current.user_id,
        email=current.email,
        full_name=current.full_name,
        role=_role_of(current),
    )


router = APIRouter(
    prefix="/risk",
    tags=["Risk"],
    dependencies=[Depends(get_current_patient)],
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


@router.post("/assess", response_model=AssessmentResult, status_code=201)
async def assess(body: AssessmentInput, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, body.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    result = await run_assessment(
        db,
        body.user_id,
        body.assessment_date,
        body.features_dict(),
    )

    await db.commit()
    return AssessmentResult(**result)


class TrendPoint(BaseModel):
    date: str
    risk_percent: float
    category: str
    emoji: str


@router.get("/trends/{user_id}", response_model=List[TrendPoint])
async def get_trends(user_id: str, db: AsyncSession = Depends(get_db)):
    q = (
        select(Assessment, RiskPrediction)
        .join(RiskPrediction, RiskPrediction.assessment_id == Assessment.assessment_id)
        .where(Assessment.user_id == user_id)
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
                category=rp.risk_level,
                emoji=_risk_emoji(risk_percent),
            )
        )
    return points


class WeeklyTrendPointOut(BaseModel):
    week_start: str
    week_label: str
    avg_risk_percent: float
    relapse_reported: bool


@router.get("/weekly-trends/{user_id}", response_model=List[WeeklyTrendPointOut])
async def get_weekly_trends(user_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    relapse_week = pg_week_start_date(WeeklyRelapseCheckin.reported_at)

    relapse_sq = (
        select(
            relapse_week.label("week_start"),
            (func.max(cast(WeeklyRelapseCheckin.actual_relapse, Integer)) == 1).label("relapse_reported"),
        )
        .where(WeeklyRelapseCheckin.user_id == user_id)
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
        .where(Assessment.user_id == user_id)
        .group_by(assess_week, relapse_sq.c.relapse_reported)
        .order_by(desc(assess_week))
        .limit(20)
    )

    rows = (await db.execute(q)).all()

    out: List[WeeklyTrendPointOut] = []
    for week_start, avg_risk, relapse_reported, week_label in reversed(rows):
        out.append(
            WeeklyTrendPointOut(
                week_start=str(week_start),
                week_label=str(week_label),
                avg_risk_percent=float(avg_risk) if avg_risk is not None else 0.0,
                relapse_reported=bool(relapse_reported),
            )
        )
    return out


@router.get("/should-show-popup/{user_id}")
async def should_show_risk_popup(user_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    n_assess = (
        await db.execute(
            select(func.count(Assessment.assessment_id)).where(Assessment.user_id == user_id)
        )
    ).scalar_one()

    if int(n_assess) < 2:
        return {"should_show": False, "reason": "need_previous_assessment"}

    latest = (
        await db.execute(
            select(RiskPrediction.predicted_risk_percent)
            .join(Assessment, RiskPrediction.assessment_id == Assessment.assessment_id)
            .where(Assessment.user_id == user_id)
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
                WeeklyRelapseCheckin.user_id == user_id,
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


@router.get("/should-show-weekly-relapse-popup/{user_id}")
async def should_show_weekly_relapse_popup(user_id: str, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")

    this_week = cast(func.date_trunc("week", func.now()), Date)

    already = (
        await db.execute(
            select(func.count(WeeklyRelapseCheckin.checkin_id)).where(
                WeeklyRelapseCheckin.user_id == user_id,
                WeeklyRelapseCheckin.week_start == this_week,
            )
        )
    ).scalar_one()

    return {"should_show": int(already) == 0, "week_start": str(this_week)}


class RelapseReportIn(BaseModel):
    user_id: str
    relapsed: int


@router.post("/relapse-report")
async def relapse_report(body: RelapseReportIn, db: AsyncSession = Depends(get_db)):
    if not await db.get(User, body.user_id):
        raise HTTPException(status_code=404, detail="User not found")

    v = 1 if int(body.relapsed) == 1 else 0
    this_week = cast(func.date_trunc("week", func.now()), Date)
    now = utcnow_aware()

    existing = (
        await db.execute(
            select(WeeklyRelapseCheckin)
            .where(
                WeeklyRelapseCheckin.user_id == body.user_id,
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
                user_id=body.user_id,
                actual_relapse=v,
                reported_at=now,
                week_start=this_week,
            )
        )

    await db.commit()
    return {
        "ok": True,
        "user_id": body.user_id,
        "relapsed": bool(v),
        "week_start": str(this_week),
    }


app.include_router(auth_router)
app.include_router(router)