from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.core.config import SECRET_KEY, ACCESS_TOKEN_MINUTES
from app.db.database import get_db
from app.db.models import Counsellor
from app.auth.security import verify_password, create_access_token, hash_password
from app.auth.deps import get_current_counsellor

router = APIRouter(prefix="/auth", tags=["auth"])


class UserOut(BaseModel):
    counsellor_id: str
    email: str
    full_name: str | None = None
    role: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# IMPORTANT:
# OAuth2PasswordRequestForm sends: username + password as application/x-www-form-urlencoded
# We will treat "username" as the counsellor email.
@router.post("/login", response_model=LoginOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = (form.username or "").strip()
    password = form.password

    user = db.query(Counsellor).filter(Counsellor.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login = func.now()
    db.commit()

    token = create_access_token(
        secret_key=SECRET_KEY,
        subject=user.counsellor_id,
        expires_minutes=ACCESS_TOKEN_MINUTES,
    )

    return LoginOut(
        access_token=token,
        user=UserOut(
            counsellor_id=user.counsellor_id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
        ),
    )


@router.get("/me", response_model=UserOut)
def me(current: Counsellor = Depends(get_current_counsellor)):
    return UserOut(
        counsellor_id=current.counsellor_id,
        email=current.email,
        full_name=current.full_name,
        role=current.role,
    )


class HashIn(BaseModel):
    password: str


class HashOut(BaseModel):
    password_hash: str


@router.post("/hash", response_model=HashOut)
def make_hash(payload: HashIn):
    return HashOut(password_hash=hash_password(payload.password))