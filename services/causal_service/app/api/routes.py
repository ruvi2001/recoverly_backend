from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from pathlib import Path
import time

from app.ml.inference import predict_top3_levels
from app.db.database import get_db
from app.db.models import Prediction, GroupSummary

from app.ml.whisper_stt import transcribe_audio
from app.core.config import UPLOAD_DIR, MAX_UPLOAD_MB

# Require counsellor login (NO sessions)
from app.auth.deps import get_current_counsellor
from app.db.models import Counsellor

router = APIRouter()

# =========================================================
# STT (Speech-to-Text) endpoints
# =========================================================

ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm", ".3gp"}

MIME_TO_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "audio/3gpp": ".3gp",
    "video/3gpp": ".3gp",
}

def _safe_ext(filename: str) -> str:
    return Path(filename).suffix.lower()

def _infer_ext(filename: str, content_type: str | None) -> str:
    ext = _safe_ext(filename or "")
    if ext:
        return ext
    if content_type:
        return MIME_TO_EXT.get(content_type.lower(), "")
    return ""

async def _save_upload(file: UploadFile, ext: str) -> Path:
    data = await file.read()

    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Max {MAX_UPLOAD_MB}MB."
        )

    ts = int(time.time() * 1000)
    saved_path = UPLOAD_DIR / f"audio_{ts}{ext}"
    saved_path.write_bytes(data)
    return saved_path


@router.post("/stt/transcribe")
async def stt_transcribe(
    file: UploadFile = File(...),
    language: str | None = Query(default=None, description="Optional: force language like 'en'"),
    keep_file: bool = Query(default=False),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    ext = _infer_ext(file.filename or "", file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Could not determine file type. Upload .mp3/.wav/.m4a/.webm/.3gp"
        )
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    saved_path = await _save_upload(file, ext)

    try:
        out = transcribe_audio(saved_path, language=language)
        return {
            "filename": file.filename,
            "saved_as": saved_path.name,
            "text": out["text"],
            "language": out.get("language"),
        }
    finally:
        if not keep_file and saved_path.exists():
            saved_path.unlink(missing_ok=True)


@router.post("/predict-from-audio")
async def predict_from_audio(
    file: UploadFile = File(...),
    user_id: str | None = Query(default=None),
    language: str | None = Query(default=None),
    keep_file: bool = Query(default=False),
    db: Session = Depends(get_db),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    ext = _infer_ext(file.filename or "", file.content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Could not determine file type. Upload .mp3/.wav/.m4a/.webm/.3gp"
        )
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    saved_path = await _save_upload(file, ext)

    try:
        stt_out = transcribe_audio(saved_path, language=language)
        transcript = (stt_out.get("text") or "").strip()
        if not transcript:
            raise HTTPException(status_code=422, detail="No speech detected in audio.")

        result = predict_top3_levels(transcript)

        top3 = result["top3"]
        top1 = top3[0] if len(top3) > 0 else {"label": None, "level": None}
        top2 = top3[1] if len(top3) > 1 else {"label": None, "level": None}
        top3_ = top3[2] if len(top3) > 2 else {"label": None, "level": None}

        row = Prediction(
            user_id=user_id,
            input_text=transcript,
            cleaned_text=result.get("cleaned_text"),
            most_impactful=result["most_impactful"],
            top1_label=top1["label"],
            top1_level=top1["level"],
            top2_label=top2["label"],
            top2_level=top2["level"],
            top3_label=top3_["label"],
            top3_level=top3_["level"],
            model_id=None,
            meta={
                "top3": result["top3"],
                "stt_language": stt_out.get("language"),
                "stt_source_filename": file.filename,
            },
        )

        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "prediction_id": row.prediction_id,
            "transcript": transcript,
            "stt_language": stt_out.get("language"),
            **result,
        }
    finally:
        if not keep_file and saved_path.exists():
            saved_path.unlink(missing_ok=True)


class PredictRequest(BaseModel):
    text: str
    user_id: str | None = None


@router.post("/predict")
def predict(
    req: PredictRequest,
    db: Session = Depends(get_db),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    result = predict_top3_levels(req.text)

    top3 = result["top3"]
    top1 = top3[0] if len(top3) > 0 else {"label": None, "level": None}
    top2 = top3[1] if len(top3) > 1 else {"label": None, "level": None}
    top3_ = top3[2] if len(top3) > 2 else {"label": None, "level": None}

    row = Prediction(
        user_id=req.user_id,
        input_text=req.text,
        cleaned_text=result.get("cleaned_text"),
        most_impactful=result["most_impactful"],
        top1_label=top1["label"],
        top1_level=top1["level"],
        top2_label=top2["label"],
        top2_level=top2["level"],
        top3_label=top3_["label"],
        top3_level=top3_["level"],
        model_id=None,
        meta={"top3": result["top3"]},
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return {"prediction_id": row.prediction_id, **result}


# ✅ UPDATED: return ids too, so frontend can delete real DB rows
@router.get("/all-patient-narratives")
def get_all_patient_narratives(
    db: Session = Depends(get_db),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    rows = db.query(Prediction).order_by(Prediction.created_at.desc()).all()

    items = [{"prediction_id": r.prediction_id, "input_text": r.input_text} for r in rows]

    # backward compatible
    return {
        "count": len(rows),
        "items": items,
        "narratives": [r.input_text for r in rows],
    }


# ✅ NEW: real delete endpoint
@router.delete("/narratives/{prediction_id}")
def delete_narrative(
    prediction_id: int,
    db: Session = Depends(get_db),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    row = db.query(Prediction).filter(Prediction.prediction_id == prediction_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Narrative not found")

    db.delete(row)
    db.commit()
    return {"ok": True, "deleted_prediction_id": prediction_id}


@router.post("/group-analysis-from-db")
def group_analysis_from_db(
    db: Session = Depends(get_db),
    _counsellor: Counsellor = Depends(get_current_counsellor),
):
    rows = (
        db.query(Prediction.most_impactful, func.count(Prediction.most_impactful))
        .group_by(Prediction.most_impactful)
        .all()
    )

    if not rows:
        return {"message": "No patient data available"}

    total = sum([r[1] for r in rows])
    distribution = {r[0]: round((r[1] / total) * 100, 2) for r in rows}

    group_row = GroupSummary(
        total_analyzed=total,
        distribution=distribution,
        model_id=None,
        meta=None,
    )

    db.add(group_row)
    db.commit()
    db.refresh(group_row)

    return {
        "group_id": group_row.group_id,
        "total_analyzed": total,
        "distribution": distribution,
    }