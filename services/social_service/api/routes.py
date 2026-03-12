"""
FastAPI Server for Recoverly Risk Service
Auth-only routes for mobile app integration
"""

import logging
import sys
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from shared.auth.jwt_utils import hash_password, verify_password, create_access_token
from shared.auth.dependencies import get_current_user_id
from shared.auth.user_repo import (
    get_user_by_email,
    get_credentials_by_user_id,
    create_user_and_credentials,
    touch_last_login,
)
from core.config import SERVICE_NAME

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


app = FastAPI(
    title=f"{SERVICE_NAME} API",
    description="Recoverly authentication service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: EmailStr
    full_name: Optional[str] = None


@app.get("/")
async def root():
    return {
        "service": SERVICE_NAME,
        "status": "operational",
        "version": "1.0.0",
    }


@app.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    username = req.email.split("@")[0]
    password_hash = hash_password(req.password)

    create_user_and_credentials(
        user_id=user_id,
        email=req.email,
        username=username,
        full_name=req.full_name,
        password_hash=password_hash,
    )

    token = create_access_token(user_id)

    return AuthResponse(
        token=token,
        user_id=user_id,
        email=req.email,
        full_name=req.full_name,
    )


@app.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    if not user or user.get("status") != "active":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    creds = get_credentials_by_user_id(user["user_id"])
    if not creds:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(req.password, creds["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    touch_last_login(user["user_id"])
    token = create_access_token(user["user_id"])

    return AuthResponse(
        token=token,
        user_id=user["user_id"],
        email=user["email"],
        full_name=user.get("full_name"),
    )


@app.get("/auth/me")
async def me(user_id: str = Depends(get_current_user_id)):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from shared.core.settings import settings

    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        options="-c search_path=core",
    )

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, email, full_name, status
                FROM core.users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            return row
    finally:
        conn.close()


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info("Auth-only API is ready")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {SERVICE_NAME}")


if __name__ == "__main__":
    import uvicorn
    from core.config import API_CONFIG

    uvicorn.run(
        "routes:app",
        host=API_CONFIG["host"],
        port=API_CONFIG["port"],
        reload=API_CONFIG["reload"],
        log_level="info",
    )