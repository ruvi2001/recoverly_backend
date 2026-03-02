import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional

from shared.core.settings import settings


def _conn():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        options="-c search_path=core",  # only core tables for auth
    )


def get_user_by_email(email: str) -> Optional[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, email, full_name, status FROM core.users WHERE email=%s",
                (email,),
            )
            return cur.fetchone()


def get_credentials_by_user_id(user_id: str) -> Optional[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, password_hash FROM core.user_credentials WHERE user_id=%s",
                (user_id,),
            )
            return cur.fetchone()


def create_user_and_credentials(
    user_id: str,
    email: str,
    username: str,
    full_name: Optional[str],
    password_hash: str,
) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO core.users (user_id, username, email, full_name, status, created_at)
                VALUES (%s, %s, %s, %s, 'active', CURRENT_TIMESTAMP)
                """,
                (user_id, username, email, full_name),
            )
            cur.execute(
                """
                INSERT INTO core.user_credentials (user_id, password_hash, created_at, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (user_id, password_hash),
            )


def touch_last_login(user_id: str) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE core.user_credentials
                SET last_login=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE user_id=%s
                """,
                (user_id,),
            )