from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from jose import jwt
from passlib.context import CryptContext
from shared.core.settings import settings

# ✅ No bcrypt. No 72-byte issues. No bcrypt backend warnings.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd.verify(password, password_hash)


def create_access_token(user_id: str, expires_minutes: int = 60) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])