from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import SECRET_KEY
from app.db.database import get_db
from app.db.models import Counsellor
from app.auth.security import decode_access_token

# This makes Swagger show the 🔒 Authorize button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_counsellor(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Counsellor:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(secret_key=SECRET_KEY, token=token)
    except Exception:
        raise credentials_exception

    counsellor_id = payload.get("sub")
    if not counsellor_id:
        raise credentials_exception

    user = (
        db.query(Counsellor)
        .filter(Counsellor.counsellor_id == counsellor_id, Counsellor.is_active == True)
        .first()
    )
    if not user:
        raise credentials_exception

    return user