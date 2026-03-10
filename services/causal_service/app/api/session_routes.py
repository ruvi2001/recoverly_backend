#C:\Users\pulni\Desktop\Recoverly_App\recoverly_backend\services\causal_service\app\api\session_routes.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.db.database import get_db
from app.db.models import ClinicSession, Counsellor
from app.auth.deps import get_current_counsellor

router = APIRouter(prefix="/sessions", tags=["sessions"])


class StartSessionIn(BaseModel):
    patient_code: str | None = None


class StartSessionOut(BaseModel):
    session_id: str
    status: str


@router.post("/start", response_model=StartSessionOut)
def start_session(
    payload: StartSessionIn,
    db: Session = Depends(get_db),
    counsellor: Counsellor = Depends(get_current_counsellor),
):
    s = ClinicSession(
        counsellor_id=counsellor.counsellor_id,
        patient_code=payload.patient_code,
        status="active",
        meta={},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return StartSessionOut(session_id=str(s.session_id), status=s.status)


@router.post("/{session_id}/end")
def end_session(
    session_id: str,
    db: Session = Depends(get_db),
    counsellor: Counsellor = Depends(get_current_counsellor),
):
    s = (
        db.query(ClinicSession)
        .filter(
            ClinicSession.session_id == session_id,
            ClinicSession.counsellor_id == counsellor.counsellor_id,
            ClinicSession.status == "active",
        )
        .first()
    )
    if not s:
        return {"ok": True, "detail": "Already ended or not found"}

    s.status = "ended"
    s.ended_at = func.now()
    db.commit()
    return {"ok": True}