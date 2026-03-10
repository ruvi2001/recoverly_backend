from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, Any
import whisper

from app.core.config import WHISPER_MODEL_NAME

_model = None

def get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(WHISPER_MODEL_NAME)
    return _model

def transcribe_audio(audio_path: str | Path, language: Optional[str] = None) -> Dict[str, Any]:
    model = get_model()
    result = model.transcribe(str(audio_path), language=language)
    return {
        "text": (result.get("text") or "").strip(),
        "language": result.get("language"),
    }