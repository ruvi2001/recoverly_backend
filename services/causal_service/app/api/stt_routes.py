# app/api/stt_routes.py
from __future__ import annotations
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pathlib import Path
import time

from app.core.config import UPLOAD_DIR, MAX_UPLOAD_MB
from app.ml.whisper_stt import transcribe_audio

router = APIRouter(prefix="/stt", tags=["Speech-to-Text"])

ALLOWED_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".webm"}

def _safe_ext(filename: str) -> str:
    return Path(filename).suffix.lower()

@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language: str | None = Query(default=None, description="Optional: force language like 'en'"),
    keep_file: bool = Query(default=False, description="Keep uploaded file on server"),
):
    ext = _safe_ext(file.filename or "")
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # size check (approx): read into bytes once
    data = await file.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"File too large ({size_mb:.1f}MB). Max {MAX_UPLOAD_MB}MB.")

    # save
    ts = int(time.time() * 1000)
    saved_path = UPLOAD_DIR / f"audio_{ts}{ext}"
    saved_path.write_bytes(data)

    try:
        out = transcribe_audio(saved_path, language=language)
        return {
            "filename": file.filename,
            "saved_as": saved_path.name,
            "text": out["text"],
            "language": out["language"],
        }
    finally:
        if not keep_file and saved_path.exists():
            saved_path.unlink(missing_ok=True)