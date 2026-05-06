"""
FastAPI Server for Recoverly Risk Monitoring System
Handles incoming messages from the mobile app and returns risk assessments
"""

from fastapi import ( FastAPI, HTTPException, Header, Depends, WebSocket, WebSocketDisconnect, Query, status, Body,)
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, constr
from typing import Optional, List
from datetime import datetime, timedelta
from services.social_service.agent.intervention_agent import get_agent
import logging
import random
import string
from psycopg2.extras import Json

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

BACKEND_ROOT = Path(__file__).resolve().parents[3]  # .../recoverly_backend
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import uuid
from pydantic import EmailStr
from shared.auth.jwt_utils import ( hash_password, verify_password, create_access_token, decode_token, )
from shared.auth.dependencies import get_current_user_id
from shared.auth.user_repo import (
    get_user_by_email,
    get_credentials_by_user_id,
    create_user_and_credentials,
    touch_last_login,
)

from core.config import API_CONFIG, MOBILE_APP_CONFIG, LOGGING_CONFIG, SERVICE_NAME
from db.temporal_engine import TemporalRiskEngine, get_engine
from ml.risk_analyzer import get_analyzer
from typing import Optional
import asyncio
from collections import defaultdict

user_processing_locks = defaultdict(asyncio.Lock)

try:
    from services.social_service.api.ws_manager import manager
except ImportError:
    from api.ws_manager import manager


# LOGGING SETUP
logging.basicConfig(
    level=LOGGING_CONFIG['level'],
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['log_file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# FASTAPI APP


app = FastAPI(
    title=f"{SERVICE_NAME} API",
    description="Agentic Support and Peer Network Facilitator - Real-time psychological risk detection",
    version="1.0.0"
)

# CORS middleware (allow mobile app to call API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: specify actual mobile app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# REQUEST/RESPONSE MODELS


class MessageRequest(BaseModel):
    """Request body for message analysis"""
    user_id: str = Field(..., description="Unique user identifier")
    message_text: str = Field(..., description="Message content", min_length=1)
    conversation_type: str = Field(default="buddy", description="'buddy' or 'counselor'")
    recipient_id: Optional[str] = Field(default=None, description="Recipient user ID")
    timestamp: Optional[datetime] = Field(default=None, description="Message timestamp (ISO format)")


class MessagePrediction(BaseModel):
    """Prediction results for a single message"""
    p_craving: float
    p_relapse: float
    p_negative_mood: float
    p_neutral: float
    p_toxic: float
    p_isolation: float
    risk_score: float


class MessageResponse(BaseModel):
    """Response after analyzing a message"""
    message_id: int
    prediction_id: int
    user_id: str
    predictions: MessagePrediction
    timestamp: datetime


class UserRiskProfile(BaseModel):
    """User's aggregated risk profile"""
    user_id: str
    current_risk_label: str
    risk_label_since: datetime
    reasons: List[str]
    short_window: dict
    medium_window: dict
    engagement: dict
    trends: dict
    last_updated: datetime

class OneToOneConversationRequest(BaseModel):
    other_user_id: str
    conversation_type: str = Field(..., pattern="^(buddy|counselor)$")

class SendChatMessageRequest(BaseModel):
    text: str = Field(..., min_length=1)

class TrustedContactIn(BaseModel):
    contact_name: str
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notify_on_high_risk: bool = True
    consent_given: bool = False


class CounselorContactIn(BaseModel):
    counselor_name: str
    clinic_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    urgent_contact_allowed: bool = False
    meeting_consent_given: bool = False


class SupportSetupIn(BaseModel):
    trusted_contact: TrustedContactIn
    counselor_contact: CounselorContactIn

class ConnectByInviteCodeRequest(BaseModel):
    invite_code: str = Field(..., min_length=4)
    conversation_type: str = Field(default="buddy", pattern="^(buddy|counselor)$")


class CounselorMeetingRequestIn(BaseModel):
    preferred_time: Optional[datetime] = None
    duration_minutes: int = Field(default=30, ge=15, le=120)
    reason: Optional[str] = None
    meeting_mode: str = Field(default="in_app_chat")

class InterventionRecommendation(BaseModel):
    """Recommended intervention for a user"""
    user_id: str
    risk_label: str
    intervention_type: str
    message: str
    urgency: str
    context: dict

# AUTHENTICATION (Simple API Key)

class RegisterRequest(BaseModel):
    email: EmailStr
    password:str = Field(min_length=1)
    full_name: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: EmailStr
    full_name: Optional[str] = None

class NudgeResponseIn(BaseModel):
    response: str = Field(default="ignored")


class EscalationAcknowledgeIn(BaseModel):
    response: str = Field(default="dismissed")

async def verify_api_key(x_api_key: str = Header(...)):
    """
    Verify API key from mobile app
    In production: use proper authentication (JWT, OAuth2)
    """
    if x_api_key != MOBILE_APP_CONFIG['api_key']:
        logger.warning(f"Invalid API key attempt: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_user_id_from_token(user_id: str = Depends(get_current_user_id)):
    return user_id

def generate_invite_code(prefix: str = "BUDDY") -> str:
    """
    Generate a readable invite code.

    Example:
    BUDDY-4821
    """
    digits = "".join(random.choices(string.digits, k=4))
    return f"{prefix}-{digits}"


def ensure_user_invite_code(engine, user_id: str) -> str:
    """
    Make sure every user has an invite code.

    No manual work is needed.
    If user already has a code, return it.
    If not, generate and save one in core.users.metadata.
    """
    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT metadata->>'invite_code' AS invite_code
            FROM core.users
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))

        row = cursor.fetchone()

        if row and row.get("invite_code"):
            return row["invite_code"]

        # Generate unique code
        for _ in range(20):
            code = generate_invite_code("BUDDY")

            cursor.execute("""
                SELECT 1
                FROM core.users
                WHERE UPPER(metadata->>'invite_code') = UPPER(%s)
                LIMIT 1
            """, (code,))

            exists = cursor.fetchone()

            if not exists:
                cursor.execute("""
                    UPDATE core.users
                    SET metadata =
                        COALESCE(metadata, '{}'::jsonb)
                        || jsonb_build_object(
                            'invite_code', %s,
                            'buddy_status', 'available'
                        )
                    WHERE user_id = %s
                    RETURNING metadata->>'invite_code' AS invite_code
                """, (code, user_id))

                updated = cursor.fetchone()
                return updated["invite_code"]

        raise HTTPException(status_code=500, detail="Could not generate invite code")


def get_user_display_name(row: dict) -> str:
    return (
        row.get("full_name")
        or (row.get("email") or "").split("@")[0]
        or row.get("username")
        or row.get("user_id")
    )


# ENDPOINTS


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": SERVICE_NAME,
        "component": "Agentic Social Support and Peer Network Facilitator",
        "status": "operational",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/auth/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    existing = get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = f"user_{uuid.uuid4().hex[:12]}"
    username = req.email.split("@")[0]

    from fastapi import HTTPException

    pw_hash = hash_password(req.password)
 
    create_user_and_credentials(
        user_id=user_id,
        email=req.email,
        username=username,
        full_name=req.full_name,
        password_hash=pw_hash,
    )

    token = create_access_token(user_id)
    return AuthResponse(token=token, user_id=user_id, email=req.email, full_name=req.full_name)


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
    # You can return full profile later; keep it simple now
    # reuse repo to fetch by email isn't possible here, so query by id quickly:
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
                "SELECT user_id, email, full_name, status FROM core.users WHERE user_id=%s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            return row
    finally:
        conn.close()

@app.post("/api/v1/support/setup")
async def save_support_setup(
    body: SupportSetupIn,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Save or replace emergency support setup for the logged-in user.
    Stores:
    - primary trusted contact
    - primary counselor contact
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        # Remove old active trusted contacts for this user
        cursor.execute("""
            DELETE FROM social.trusted_contacts
            WHERE user_id = %s
        """, (user_id,))

        # Remove old active counselor contact for this user
        cursor.execute("""
            DELETE FROM social.user_counselor_contacts
            WHERE user_id = %s
        """, (user_id,))

        # Insert trusted contact
        cursor.execute("""
            INSERT INTO social.trusted_contacts (
                user_id,
                contact_name,
                relationship,
                phone,
                email,
                notify_on_high_risk,
                is_primary,
                consent_given,
                consent_given_at,
                status,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                TRUE,
                %s,
                CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                'active',
                CURRENT_TIMESTAMP
            )
        """, (
            user_id,
            body.trusted_contact.contact_name,
            body.trusted_contact.relationship,
            body.trusted_contact.phone,
            body.trusted_contact.email,
            body.trusted_contact.notify_on_high_risk,
            body.trusted_contact.consent_given,
            body.trusted_contact.consent_given,
        ))

        # Insert counselor contact
        cursor.execute("""
            INSERT INTO social.user_counselor_contacts (
                user_id,
                counselor_name,
                clinic_name,
                phone,
                email,
                urgent_contact_allowed,
                meeting_consent_given,
                consent_given_at,
                status,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                CASE
                    WHEN %s OR %s THEN CURRENT_TIMESTAMP
                    ELSE NULL
                END,
                'active',
                CURRENT_TIMESTAMP
            )
        """, (
            user_id,
            body.counselor_contact.counselor_name,
            body.counselor_contact.clinic_name,
            body.counselor_contact.phone,
            body.counselor_contact.email,
            body.counselor_contact.urgent_contact_allowed,
            body.counselor_contact.meeting_consent_given,
            body.counselor_contact.urgent_contact_allowed,
            body.counselor_contact.meeting_consent_given,
        ))

    return {
        "ok": True,
        "message": "Emergency support setup saved successfully"
    }

@app.get("/api/v1/support/setup")
async def get_support_setup(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return current trusted contact + counselor contact for logged-in user.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                contact_id,
                contact_name,
                relationship,
                phone,
                email,
                notify_on_high_risk,
                is_primary,
                consent_given,
                consent_given_at,
                status,
                created_at
            FROM social.trusted_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY is_primary DESC, created_at DESC
            LIMIT 1
        """, (user_id,))
        trusted_contact = cursor.fetchone()

        cursor.execute("""
            SELECT
                counselor_contact_id,
                counselor_name,
                clinic_name,
                phone,
                email,
                urgent_contact_allowed,
                meeting_consent_given,
                consent_given_at,
                status,
                created_at
            FROM social.user_counselor_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        counselor_contact = cursor.fetchone()

    return {
        "trusted_contact": trusted_contact,
        "counselor_contact": counselor_contact,
    }

@app.get("/api/v1/trusted-contact/primary")
async def get_primary_trusted_contact(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return the primary trusted contact for the logged-in user.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                contact_id,
                contact_name,
                relationship,
                phone,
                email,
                notify_on_high_risk,
                is_primary,
                consent_given,
                consent_given_at,
                status,
                created_at
            FROM social.trusted_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY is_primary DESC, created_at DESC
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()

    return row

@app.get("/api/v1/counselor-contact/primary")
async def get_primary_counselor_contact(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return the primary counselor contact for the logged-in user.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                counselor_contact_id,
                counselor_name,
                clinic_name,
                phone,
                email,
                urgent_contact_allowed,
                meeting_consent_given,
                consent_given_at,
                status,
                created_at
            FROM social.user_counselor_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        row = cursor.fetchone()

    return row

@app.post("/api/v1/trusted-contact/notify")
async def notify_trusted_contact(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Prototype trusted-contact escalation.
    For demo:
    - fetch primary trusted contact
    - check consent
    - log a support action
    - return notification-ready status

    In production:
    - integrate SMS / WhatsApp / voice / email service here
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        # Get primary trusted contact
        cursor.execute("""
            SELECT
                contact_id,
                contact_name,
                relationship,
                phone,
                email,
                notify_on_high_risk,
                consent_given
            FROM social.trusted_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY is_primary DESC, created_at DESC
            LIMIT 1
        """, (user_id,))
        contact = cursor.fetchone()

        if not contact:
            raise HTTPException(
                status_code=404,
                detail="No trusted contact found for this user"
            )

        if not contact.get("consent_given"):
            raise HTTPException(
                status_code=400,
                detail="Trusted contact consent not available"
            )

        if not contact.get("notify_on_high_risk"):
            raise HTTPException(
                status_code=400,
                detail="Trusted contact notifications are disabled"
            )

        # Log action in social.actions
        cursor.execute("""
            INSERT INTO social.actions (
                user_id,
                timestamp,
                action_type,
                risk_level,
                action_data,
                status,
                ai_reasoning,
                confidence_score
            )
            VALUES (
                %s,
                CURRENT_TIMESTAMP,
                %s,
                %s,
                %s::jsonb,
                %s,
                %s,
                %s
            )
            RETURNING action_id
        """, (
            user_id,
            "trusted_contact_notification",
            "HIGH_RISK",
            f"""{{
                "contact_id": {contact["contact_id"]},
                "contact_name": "{contact["contact_name"]}",
                "relationship": "{contact.get("relationship") or ""}",
                "phone": "{contact.get("phone") or ""}",
                "email": "{contact.get("email") or ""}",
                "mode": "demo_simulation"
            }}""",
            "completed",
            "Trusted contact escalation prepared for high-risk support flow",
            0.95,
        ))
        action = cursor.fetchone()

    return {
        "ok": True,
        "message": "Trusted contact notification prepared",
        "mode": "demo_simulation",
        "action_id": action["action_id"] if action else None,
        "contact": contact,
        "notification_status": "prepared"
    }

@app.get("/api/v1/trusted-contact/support/current")
async def get_current_trusted_contact_support(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return latest trusted-contact related support action for the logged-in user.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                action_id,
                action_type,
                risk_level,
                action_data,
                status,
                timestamp,
                ai_reasoning,
                confidence_score
            FROM social.actions
            WHERE user_id = %s
              AND action_type = 'trusted_contact_notification'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        action = cursor.fetchone()

        cursor.execute("""
            SELECT
                contact_id,
                contact_name,
                relationship,
                phone,
                email,
                notify_on_high_risk,
                consent_given
            FROM social.trusted_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY is_primary DESC, created_at DESC
            LIMIT 1
        """, (user_id,))
        contact = cursor.fetchone()

    return {
        "user_id": user_id,
        "has_active_support": bool(action or contact),
        "trusted_contact": contact,
        "latest_action": action,
        "message": "Trusted contact support is available" if contact else "No trusted contact configured"
    }

@app.get("/auth/users")
async def get_all_users(user_id: str = Depends(get_current_user_id)):
    """
    Get list of all registered users
    Requires authentication
    """
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
                "SELECT user_id, email, full_name FROM core.users WHERE status = 'active' ORDER BY email"
            )
            rows = cur.fetchall()
            return {"users": rows}
    finally:
        conn.close()


@app.post("/api/v1/analyze-message", response_model=MessageResponse)
async def analyze_message(
    request: MessageRequest,
    api_key: str = Depends(verify_api_key)
):
    """
    Analyze a single message and store predictions
    Called by Recoverly mobile app when user sends a message
    
    Workflow:
    1. Ensure user exists in core.users
    2. Run ML models (risk + isolation detection)
    3. Store message in core.messages
    4. Store predictions in social.message_predictions
    5. Return predictions to app    

    """
    try:
        logger.info(f"Analyzing message from user: {request.user_id}")
        
        # Get analyzer and engine
        analyzer = get_analyzer()
        engine = get_engine()

        # Ensure user exists in core.users (important for FK constraint)
        engine.ensure_user_exists(request.user_id)
        
        # Run ML models
        predictions = analyzer.analyze_message(request.message_text)
        logger.debug(f"Predictions: {predictions}")
        
        # Store in database
        message_id, prediction_id = engine.store_message_with_prediction(
            user_id=request.user_id,
            message_text=request.message_text,
            predictions=predictions,
            conversation_type=request.conversation_type,
            recipient_id=request.recipient_id,
            timestamp=request.timestamp
        )
        
        logger.info(f"Stored message {message_id} for user {request.user_id}")

        # AUTO-UPDATE USER RISK PROFILE

        thresholds = analyzer.get_thresholds()
        profile = engine.update_user_risk_profile(request.user_id,thresholds)
        logger.info(f"Updated risk profile: {profile['current_risk_label']}")

        # Trigger agent
        agent = get_agent(engine)
        actions = agent.process_user(profile)
        logger.info(f"Auto-triggered {len(actions)} interventions for {request.user_id}")

        # # AUTO-TRIGGER RISK CHECK (if message has high risk)
        # if predictions['risk_score'] > 0.7:  # Threshold
        #     logger.info(f"High-risk message detected - triggering intervention check")
            
        #     # Update risk profile
        #     profile = engine.update_user_risk_profile(request.user_id, thresholds)
            
             
        # Return results
        return MessageResponse(
            message_id=message_id,
            prediction_id=prediction_id,
            user_id=request.user_id,
            predictions=MessagePrediction(**predictions),
            # message_level_risk="informational_only",  # Not used for decisions
            timestamp=request.timestamp or datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error analyzing message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/user-risk/{user_id}", response_model=UserRiskProfile)
async def get_user_risk(
    user_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Get complete risk profile for a user
    
    Triggers temporal aggregation:
    - Analyzes last 7-30 days of messages
    - Computes risk trends
    - Detects engagement patterns
    - Returns final risk label (HIGH/MODERATE/LOW/ISOLATION)
    """
    try:
        logger.info(f"Computing risk profile for user: {user_id}")
        
        # Get engine and analyzer
        engine = get_engine()
        analyzer = get_analyzer()
        thresholds = analyzer.get_thresholds()
        
        # Compute risk profile
        profile = engine.update_user_risk_profile(user_id, thresholds)

        logger.info(f"User {user_id}: {profile['current_risk_label']}")
        
        return UserRiskProfile(**profile)
        
    except Exception as e:
        logger.error(f"Error computing user risk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/trigger-risk-check/{user_id}")
async def trigger_risk_check(
    user_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Manually trigger a risk assessment and potential intervention
    
    Can be called:
    - After a user sends a message (if you want immediate check)
    - On a schedule (every hour, check all users)
    - When a user logs in (to catch silent users)
    """
    try:
        logger.info(f"Manual risk check triggered for: {user_id}")
        
        # Get engine and analyzer
        engine = get_engine()
        analyzer = get_analyzer()
        thresholds = analyzer.get_thresholds()
        
        # Compute risk profile
        profile = engine.update_user_risk_profile(user_id, thresholds)
        
        # Trigger intervention agent
        agent = get_agent(engine)
        actions = agent.process_user(profile)
        
        return {
            "user_id": user_id,
            "risk_label": profile['current_risk_label'],
            "reasons": profile['reasons'],
            "check_completed": True,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in risk check: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/users-needing-checkin")
async def get_users_needing_checkin(
    days_silent: int = 3,
    api_key: str = Depends(verify_api_key)
):
    """
    Get list of users who haven't messaged buddies in N days
    
    This endpoint can be called periodically to identify users
    who need a check-in nudge
    """
    try:
        logger.info(f"Finding users silent for >{days_silent} days")
        
        engine = get_engine()
        silent_users = engine.get_users_needing_check_in(days_silent)

        logger.info(f"Found {len(silent_users)} users needing check-in")
        
        return {
            "silent_user_count": len(silent_users),
            "user_ids": silent_users,
            "days_threshold": days_silent,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting silent users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/all-users")
async def get_all_users(
    api_key: str = Depends(verify_api_key)
):
    """
    Get risk profiles for all users (for counselor dashboard)
    
    Returns users sorted by risk priority:
    HIGH_RISK → MODERATE_RISK → ISOLATION_ONLY → LOW_RISK
    """
    try:
        logger.info("Fetching all user profiles")
        
        engine = get_engine()
        profiles = engine.get_all_user_profiles()
        
        return {
            "total_users": len(profiles),
            "users": profiles,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching all users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/stats")
async def get_system_stats(
    api_key: str = Depends(verify_api_key)
):
    """
    Get overall system statistics
    """
    try:
        engine = get_engine()
        profiles = engine.get_all_user_profiles()
        
        # Count by risk label
        risk_distribution = {}
        for profile in profiles:
            label = profile.get('risk_label', 'UNKNOWN')
            risk_distribution[label] = risk_distribution.get(label, 0) + 1
        
        return {
            "total_users": len(profiles),
            "risk_distribution": risk_distribution,
            "high_risk_count": risk_distribution.get('HIGH_RISK', 0),
            "moderate_risk_count": risk_distribution.get('MODERATE_RISK', 0),
            "isolation_only_count": risk_distribution.get('ISOLATION_ONLY', 0),
            "low_risk_count": risk_distribution.get('LOW_RISK', 0),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/v1/buddy/invite-code")
async def get_my_invite_code(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return the logged-in user's invite code.

    This can be displayed in PeerConnectScreen:
    'Share this code with a buddy: BUDDY-4821'
    """
    engine = get_engine()
    code = ensure_user_invite_code(engine, user_id)

    return {
        "user_id": user_id,
        "invite_code": code,
        "message": "Share this code only with someone you trust."
    }


@app.get("/api/v1/buddy/suggestions")
async def get_buddy_suggestions(
    limit: int = 10,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return suggested buddies.

    This does not show all users blindly.
    It excludes:
    - current user
    - users already connected in a buddy conversation

    It prefers active users and users with low/moderate/unknown risk.
    """
    engine = get_engine()

    ensure_user_invite_code(engine, user_id)

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                u.user_id,
                u.username,
                u.email,
                u.full_name,
                u.last_active,
                u.metadata->>'invite_code' AS invite_code,
                COALESCE(r.current_risk_label, 'UNKNOWN') AS current_risk_label,
                COALESCE(r.total_messages_7d, 0) AS total_messages_7d,
                COALESCE(r.days_since_last_buddy_msg, 999) AS days_since_last_buddy_msg
            FROM core.users u
            LEFT JOIN social.user_risk_profiles r
                ON r.user_id = u.user_id
            WHERE u.status = 'active'
              AND u.user_id <> %s

              -- Exclude users already connected with me in buddy conversation
              AND NOT EXISTS (
                  SELECT 1
                  FROM core.conversations c
                  JOIN core.conversation_participants me
                    ON me.conversation_id = c.conversation_id
                  JOIN core.conversation_participants other
                    ON other.conversation_id = c.conversation_id
                  WHERE c.conversation_type = 'buddy'
                    AND me.user_id = %s
                    AND other.user_id = u.user_id
              )

            ORDER BY
                CASE
                    WHEN r.current_risk_label IN ('LOW_RISK', 'MODERATE_RISK') THEN 1
                    WHEN r.current_risk_label IS NULL THEN 2
                    ELSE 3
                END ASC,
                COALESCE(u.last_active, u.created_at) DESC
            LIMIT %s
        """, (user_id, user_id, limit))

        rows = cursor.fetchall()

    suggestions = []

    for row in rows:
        suggestions.append({
            "user_id": row["user_id"],
            "name": get_user_display_name(row),
            "email": row.get("email"),
            "invite_code": row.get("invite_code"),
            "risk_label": row.get("current_risk_label"),
            "total_messages_7d": row.get("total_messages_7d"),
            "days_since_last_buddy_msg": row.get("days_since_last_buddy_msg"),
            "reason": "Suggested as an available recovery peer"
        })

    return {
        "suggestions": suggestions,
        "count": len(suggestions)
    }


@app.post("/api/v1/buddy/connect-by-code")
async def connect_by_invite_code(
    body: ConnectByInviteCodeRequest,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Connect to another user using invite code.

    Example:
    Patient enters BUDDY-4821
    Backend finds the matching user
    Backend creates buddy conversation
    """
    engine = get_engine()

    code = body.invite_code.strip().upper()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                user_id,
                username,
                email,
                full_name,
                metadata->>'invite_code' AS invite_code
            FROM core.users
            WHERE status = 'active'
              AND UPPER(metadata->>'invite_code') = %s
            LIMIT 1
        """, (code,))

        target = cursor.fetchone()

    if not target:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    other_user_id = target["user_id"]

    if other_user_id == user_id:
        raise HTTPException(status_code=400, detail="You cannot connect with yourself")

    conversation_id = engine.get_or_create_one_to_one_conversation(
        user_id=user_id,
        other_user_id=other_user_id,
        conversation_type=body.conversation_type,
    )

    return {
        "conversation_id": conversation_id,
        "conversation_type": body.conversation_type,
        "other_user": {
            "user_id": other_user_id,
            "name": get_user_display_name(target),
            "email": target.get("email"),
        },
        "message": "Connection created successfully"
    }

@app.post("/chat/conversations/one-to-one")
async def create_or_get_one_to_one(
    body: OneToOneConversationRequest,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    engine.ensure_user_exists(user_id)
    engine.ensure_user_exists(body.other_user_id)

    cid = engine.get_or_create_one_to_one_conversation(user_id, body.other_user_id, body.conversation_type)
    return {"conversation_id": cid}


@app.get("/chat/conversations")
async def list_my_conversations(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    return {"conversations": engine.list_conversations_for_user(user_id)}


@app.get("/chat/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    limit: int = 50,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key)
):
    """
    Get visible messages for current user.

    Soft-deleted messages return:
    message_text = 'This message was deleted'
    deleted_for_everyone = true
    """
    engine = get_engine()
    engine.assert_user_in_conversation(conversation_id, user_id)

    return {
        "messages": engine.get_messages(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit
        )
    }

@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation_for_me(
    conversation_id: int,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Delete/clear chat for current user only.

    This does not delete the real conversation or real messages.
    It only hides old messages from this user's UI.
    """
    try:
        engine = get_engine()

        result = engine.delete_conversation_for_user(
            conversation_id=conversation_id,
            user_id=user_id,
        )

        # If WebSocket exists, notify this user's open chat screen
        if manager is not None:
            try:
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "conversation_deleted_for_me",
                        "data": {
                            "conversation_id": conversation_id,
                        },
                    },
                )
            except Exception:
                pass

        return {
            "ok": True,
            "message": "Conversation hidden for this user",
            "data": result,
        }

    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except Exception as e:
        logger.error(f"delete_conversation_for_me error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
@app.delete("/chat/conversations/{conversation_id}/messages/{message_id}/everyone")
async def delete_message_for_everyone(
    conversation_id: int,
    message_id: int,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Soft delete a message for everyone.

    Rules:
    - current user must be in the conversation
    - current user must be the sender of the message
    - original message remains in core.messages for analysis
    - social.message_predictions remains untouched
    """
    try:
        engine = get_engine()

        result = engine.soft_delete_message_for_everyone(
            conversation_id=conversation_id,
            message_id=message_id,
            user_id=user_id,
        )

        event_payload = {
            "event": "message_deleted_for_everyone",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "deleted_by": user_id,
                "message_text": "This message was deleted",
                "deleted_for_everyone": True,
            },
        }

        # If WebSocket exists, notify both users immediately
        if manager is not None:
            try:
                await manager.broadcast_to_conversation(
                    conversation_id,
                    event_payload,
                )
            except Exception:
                pass

        return {
            "ok": True,
            "message": "Message deleted for everyone",
            "data": result,
        }

    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"delete_message_for_everyone error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def get_user_id_from_ws_token(token: str) -> str:
    """
    Decode JWT token for WebSocket requests.

    REST uses Authorization header.
    WebSocket uses query parameter:
    /ws/chat/1?token=JWT&api_key=mobile_app_key_12345
    """
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise ValueError("Missing user_id in token")

        return user_id
    except Exception:
        raise ValueError("Invalid or expired token")


def fetch_next_intervention_payload(engine, user_id: str) -> dict:
    """
    Same logic as /api/v1/interventions/next.

    Needed because after a WebSocket message is analyzed,
    frontend should receive the popup event immediately.
    """
    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                escalation_id,
                escalation_type,
                urgency,
                risk_score,
                risk_level,
                trigger_reason,
                timestamp
            FROM social.escalations
            WHERE user_id = %s
              AND status = 'pending'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))

        esc = cursor.fetchone()

        if esc:
            return {
                "type": "HIGH",
                "source": "escalation",
                "payload": esc,
            }

        cursor.execute("""
            SELECT
                nudge_id,
                nudge_type,
                nudge_message,
                risk_level,
                sent_at,
                viewed_at,
                acted_on_at,
                user_response
            FROM social.nudges
            WHERE user_id = %s
              AND sent_at IS NOT NULL
              AND viewed_at IS NULL
              AND COALESCE(UPPER(risk_level), '') NOT LIKE '%%HIGH%%'
            ORDER BY sent_at DESC
            LIMIT 1
        """, (user_id,))

        nudge = cursor.fetchone()

        if nudge:
            lvl = (nudge.get("risk_level") or "").upper()

            if "MODERATE" in lvl:
                ui_type = "MEDIUM"
            else:
                ui_type = "LOW"

            return {
                "type": ui_type,
                "source": "nudge",
                "payload": nudge,
            }

    return {
        "type": "NONE",
        "source": None,
        "payload": None,
    }


def fetch_current_counselor_support_payload(engine, user_id: str) -> dict:
    """
    Return latest counselor support data.

    This matches what CounselorSupportScreen already shows.
    """
    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                escalation_id,
                escalation_type,
                urgency,
                risk_score,
                risk_level,
                trigger_reason,
                escalated_to,
                notification_method,
                status,
                timestamp,
                acknowledged_at,
                resolved_at
            FROM social.escalations
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        escalation = cursor.fetchone()

        cursor.execute("""
            SELECT
                meeting_id,
                meeting_type,
                scheduled_time,
                duration_minutes,
                counselor_id,
                status,
                created_at,
                notes
            FROM social.meetings
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        meeting = cursor.fetchone()

        cursor.execute("""
            SELECT
                action_id,
                action_type,
                risk_level,
                action_data,
                status,
                timestamp
            FROM social.actions
            WHERE user_id = %s
              AND action_type IN ('counselor_alert', 'urgent_meeting_scheduled')
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        action = cursor.fetchone()

    return {
        "user_id": user_id,
        "has_active_support": bool(escalation or meeting or action),
        "escalation": escalation,
        "meeting": meeting,
        "action": action,
        "message": "Urgent counselor support requested"
        if (escalation or meeting or action)
        else "No active counselor support request",
    }


def process_chat_message(conversation_id: int, user_id: str, text: str) -> dict:
    """
    Main chat pipeline used by both REST and WebSocket.

    Steps:
    1. Confirm user belongs to conversation
    2. Find recipient
    3. Get conversation_type from DB
    4. Run existing RiskAnalyzer
    5. Save message in core.messages
    6. Save prediction in social.message_predictions
    7. Update social.user_risk_profiles
    8. Run InterventionAgent
    9. Return message + intervention result
    """
    clean_text = text.strip()

    if not clean_text:
        raise ValueError("Message text cannot be empty")

    engine = get_engine()
    engine.assert_user_in_conversation(conversation_id, user_id)

    recipient_id = engine.get_other_participant(conversation_id, user_id)
    conversation_type = engine.get_conversation_type(conversation_id)

    analyzer = get_analyzer()
    predictions = analyzer.analyze_message(clean_text)

    timestamp = datetime.now()

    message_id, prediction_id = engine.store_message_with_prediction(
        user_id=user_id,
        message_text=clean_text,
        predictions=predictions,
        conversation_type=conversation_type,
        recipient_id=recipient_id,
        conversation_id=conversation_id,
        timestamp=timestamp,
    )

    thresholds = analyzer.get_thresholds()
    profile = engine.update_user_risk_profile(user_id, thresholds)

    agent = get_agent(engine)
    actions = agent.process_user(profile)

    intervention = fetch_next_intervention_payload(engine, user_id)

    counselor_support = None

    if intervention.get("type") == "HIGH":
        counselor_support = fetch_current_counselor_support_payload(engine, user_id)

    return {
        "message": {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "recipient_id": recipient_id,
            "message_text": clean_text,
            "timestamp": timestamp,
            "conversation_type": conversation_type,
        },
        "prediction_id": prediction_id,
        "predictions": predictions,
        "risk_profile": profile,
        "actions": actions,
        "intervention": intervention,
        "counselor_support": counselor_support,
    }

@app.post("/chat/conversations/{conversation_id}/messages")
async def send_message_rest(
    conversation_id: int,
    body: SendChatMessageRequest,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    REST fallback for message sending.

    WebSocket will be the main live-chat method.
    REST remains as backup if WebSocket is disconnected.
    """
    try:
        async with user_processing_locks[user_id]:
         result = process_chat_message(
            conversation_id=conversation_id,
            user_id=user_id,
            text=body.text,
        )

        return jsonable_encoder(result)

    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    except Exception as e:
        logger.error(f"send_message_rest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/interventions/next")
async def get_next_intervention(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Returns the next pending intervention UI item for the user.
    Priority:
    1) HIGH: pending escalation
    2) MED/LOW: latest unviewed nudge
    3) NONE
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        # 1) Escalations first (HIGH)
        cursor.execute("""
            SELECT escalation_id, escalation_type, urgency, risk_score, risk_level,
                   trigger_reason, timestamp
            FROM social.escalations
            WHERE user_id = %s
              AND status = 'pending'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        esc = cursor.fetchone()
        if esc:
            return {
                "type": "HIGH",
                "source": "escalation",
                "payload": esc,
            }

        # 2) Unviewed nudges (LOW/MEDIUM)
        cursor.execute("""
            SELECT nudge_id, nudge_type, nudge_message, risk_level, sent_at, viewed_at, acted_on_at,user_response
            FROM social.nudges
            WHERE user_id = %s
              AND sent_at IS NOT NULL
              AND viewed_at IS NULL
              AND COALESCE(UPPER(risk_level), '') NOT LIKE '%%HIGH%%'
            ORDER BY sent_at DESC
            LIMIT 1
        """, (user_id,))

        nudge = cursor.fetchone()

        if nudge:
            # Decide UI type based on risk_level stored with nudge
            lvl = (nudge.get("risk_level") or "").upper()
            
            if "MODERATE" in lvl:
                    ui_type = "MEDIUM"
            else:
                ui_type = "LOW"

            return {"type": ui_type, "source": "nudge", "payload": nudge}
        
    return {"type": "NONE", "source": None, "payload": None}

@app.post("/api/v1/interventions/nudges/{nudge_id}/viewed")
@app.post("/api/v1/interventions/nudges/{nudge_id}/view")
async def mark_nudge_viewed(
    nudge_id: int,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Mark a LOW/MEDIUM nudge as viewed.
    """
    engine = get_engine()
    with engine.get_cursor() as cursor:
        cursor.execute("""
            UPDATE social.nudges
            SET viewed_at = COALESCE(viewed_at, CURRENT_TIMESTAMP)
            WHERE nudge_id = %s AND user_id = %s
            RETURNING nudge_id, user_id, risk_level, viewed_at, acted_on_at, user_response 
        """, (nudge_id, user_id))

        row = cursor.fetchone()
        
    if not row:
        raise HTTPException(status_code=404, detail="Nudge not found")
    
    return {
        "ok" : True,
        "message": "Nudge Viewed",
        "nudge": row,
    }

@app.post("/api/v1/interventions/nudges/{nudge_id}/respond")
async def respond_to_nudge(
    nudge_id: int,
    body: Optional[NudgeResponseIn] = Body(default=None),
    response: Optional[str] = Query(default=None),
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Mark LOW/MEDIUM popup as handled.

    Supports both:
    1. JSON body: { "response": "ignored" }
    2. Query param: ?response=ignored
    """
    engine = get_engine()

    selected_response = (
        response
        or (body.response if body else None)
        or "ignored"
    ).lower().strip()

    allowed = (
        "positive",
        "negative",
        "ignored",
        "dismissed",
        "talk_to_peer",
        "message_counselor",
        "im_okay",
        "closed_by_user",
    )

    if selected_response not in allowed:
        selected_response = "ignored"

    with engine.get_cursor() as cursor:
        cursor.execute("""
            UPDATE social.nudges
            SET
                user_response = %s,
                viewed_at = COALESCE(viewed_at, CURRENT_TIMESTAMP),
                acted_on_at = COALESCE(acted_on_at, CURRENT_TIMESTAMP)
            WHERE nudge_id = %s 
              AND user_id = %s      
            RETURNING
                nudge_id,
                user_id,
                nudge_type,
                risk_level,
                viewed_at,
                acted_on_at,
                user_response
        """, (selected_response, nudge_id, user_id))

        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Nudge not found")

    return {
        "ok": True,
        "message": "Nudge handled",
        "nudge": row,
    }

@app.post("/api/v1/interventions/escalations/{escalation_id}/acknowledge")
async def acknowledge_escalation(
    escalation_id: int,
    body: Optional[EscalationAcknowledgeIn] = Body(default=None),
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Mark HIGH-risk popup as handled.

    This changes escalation from pending -> acknowledged.
    Then getNextIntervention() will stop returning it.
    """
    engine = get_engine()

    selected_response = (
        body.response if body else "dismissed"
    ).lower().strip()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            UPDATE social.escalations
            SET
                status = 'acknowledged',
                acknowledged_at = COALESCE(acknowledged_at, CURRENT_TIMESTAMP),
                resolution_notes = COALESCE(resolution_notes, '') || %s
            WHERE escalation_id = %s
              AND user_id = %s
              AND status = 'pending'
            RETURNING
                escalation_id,
                user_id,
                escalation_type,
                urgency,
                risk_level,
                status,
                acknowledged_at,
                resolution_notes
        """, (
            f'\nUser popup response: {selected_response}',
            escalation_id,
            user_id,
        ))

        escalation = cursor.fetchone()

        cursor.execute("""
            UPDATE social.nudges
            SET
                viewed_at = COALESCE(viewed_at, CURRENT_TIMESTAMP),
                acted_on_at = COALESCE(acted_on_at, CURRENT_TIMESTAMP),
                user_response = COALESCE(user_response, %s)
            WHERE user_id = %s
              AND viewed_at IS NULL
              AND COALESCE(UPPER(risk_level), '') LIKE '%%HIGH%%'
            RETURNING
                nudge_id,
                user_id,
                risk_level,
                viewed_at,
                acted_on_at,
                user_response
        """, (
            f"high_popup_{selected_response}",
            user_id,
        ))

        cleared_high_nudges = cursor.fetchall()

    return {
        "ok": True,
        "message": "Escalation acknowledged",
        "escalation": escalation,
        "cleared_high_nudges": cleared_high_nudges,
    }
@app.post("/api/v1/meetings/request")
async def request_counselor_meeting(
    body: CounselorMeetingRequestIn,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Create a counselor meeting request.

    This does not require a counselor dashboard.
    It uses the counselor contact saved in EmergencySupportSetupScreen.

    It creates:
    1. social.meetings row
    2. social.actions row representing counselor notification/message prepared
    """
    engine = get_engine()

    requested_time = body.preferred_time or (datetime.now() + timedelta(hours=2))
    reason = body.reason or "User requested counselor support from Recoverly app"

    with engine.get_cursor() as cursor:
        # 1. Get active counselor contact
        cursor.execute("""
            SELECT
                counselor_contact_id,
                counselor_name,
                clinic_name,
                phone,
                email,
                urgent_contact_allowed,
                meeting_consent_given
            FROM social.user_counselor_contacts
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))

        counselor = cursor.fetchone()

        if not counselor:
            raise HTTPException(
                status_code=404,
                detail="No counselor contact configured. Please complete emergency support setup first."
            )

        # 2. Create meeting request
        participants = {
            "user_id": user_id,
            "counselor_contact_id": counselor["counselor_contact_id"],
            "counselor_name": counselor["counselor_name"],
            "clinic_name": counselor.get("clinic_name"),
            "email": counselor.get("email"),
            "phone": counselor.get("phone"),
            "meeting_mode": body.meeting_mode,
        }

        cursor.execute("""
            INSERT INTO social.meetings (
                user_id,
                meeting_type,
                scheduled_time,
                duration_minutes,
                counselor_id,
                participants,
                user_consent,
                consent_given_at,
                status,
                notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, CURRENT_TIMESTAMP, %s, %s)
            RETURNING
                meeting_id,
                user_id,
                meeting_type,
                scheduled_time,
                duration_minutes,
                counselor_id,
                participants,
                user_consent,
                status,
                created_at,
                notes
        """, (
            user_id,
            "counselor",
            requested_time,
            body.duration_minutes,
            f"counselor_contact:{counselor['counselor_contact_id']}",
            Json(participants),
            "pending_counselor_confirmation",
            reason,
        ))

        meeting = cursor.fetchone()

        # 3. Log counselor notification/message as an action
        notification_payload = {
            "mode": "demo_simulation",
            "notification_type": "counselor_meeting_request",
            "meeting_id": meeting["meeting_id"],
            "requested_time": requested_time.isoformat(),
            "duration_minutes": body.duration_minutes,
            "reason": reason,
            "counselor_name": counselor["counselor_name"],
            "clinic_name": counselor.get("clinic_name"),
            "email": counselor.get("email"),
            "phone": counselor.get("phone"),
            "message": (
                f"Recoverly meeting request: user {user_id} requested "
                f"a counselor meeting around {requested_time.isoformat()}."
            ),
        }

        cursor.execute("""
            INSERT INTO social.actions (
                user_id,
                timestamp,
                action_type,
                risk_level,
                action_data,
                status,
                ai_reasoning,
                confidence_score
            )
            VALUES (
                %s,
                CURRENT_TIMESTAMP,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING action_id, status
        """, (
            user_id,
            "counselor_meeting_request_notification",
            "USER_REQUEST",
            Json(notification_payload),
            "completed",
            "Counselor meeting request prepared using configured counselor contact",
            0.95,
        ))

        action = cursor.fetchone()

    return {
        "ok": True,
        "message": "Counselor meeting request created",
        "notification_status": "prepared",
        "meeting": meeting,
        "counselor": counselor,
        "action": action,
    }


@app.get("/api/v1/meetings/my")
async def get_my_meetings(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return user's meeting requests.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            SELECT
                meeting_id,
                meeting_type,
                scheduled_time,
                duration_minutes,
                counselor_id,
                participants,
                user_consent,
                status,
                created_at,
                completed_at,
                notes
            FROM social.meetings
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (user_id,))

        rows = cursor.fetchall()

    return {
        "meetings": rows,
        "count": len(rows)
    }


@app.post("/api/v1/meetings/{meeting_id}/cancel")
async def cancel_meeting_request(
    meeting_id: int,
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Cancel user's own meeting request.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        cursor.execute("""
            UPDATE social.meetings
            SET status = 'cancelled',
                notes = COALESCE(notes, '') || E'\nCancelled by user from mobile app.'
            WHERE meeting_id = %s
              AND user_id = %s
            RETURNING meeting_id, status
        """, (meeting_id, user_id))

        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "ok": True,
        "meeting": row
    }

@app.get("/api/v1/interventions/counselor-support/current")
async def get_current_counselor_support(
    user_id: str = Depends(get_user_id_from_token),
    api_key: str = Depends(verify_api_key),
):
    """
    Return latest counselor-support related escalation + meeting + action
    for the currently logged-in user.
    """
    engine = get_engine()

    with engine.get_cursor() as cursor:
        # latest escalation
        cursor.execute("""
            SELECT
                escalation_id,
                escalation_type,
                urgency,
                risk_score,
                risk_level,
                trigger_reason,
                escalated_to,
                notification_method,
                status,
                timestamp,
                acknowledged_at,
                resolved_at
            FROM social.escalations
            WHERE user_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        escalation = cursor.fetchone()

        # latest urgent/emergency meeting
        cursor.execute("""
            SELECT
                meeting_id,
                meeting_type,
                scheduled_time,
                duration_minutes,
                counselor_id,
                status,
                created_at,
                notes
            FROM social.meetings
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,))
        meeting = cursor.fetchone()

        # latest counselor-related action
        cursor.execute("""
            SELECT
                action_id,
                action_type,
                risk_level,
                action_data,
                status,
                timestamp
            FROM social.actions
            WHERE user_id = %s
              AND action_type IN ('counselor_alert', 'urgent_meeting_scheduled', 'counselor_meeting_request_notification')
            ORDER BY timestamp DESC
            LIMIT 1
        """, (user_id,))
        action = cursor.fetchone()

    return {
        "user_id": user_id,
        "has_active_support": bool(escalation or meeting or action),
        "escalation": escalation,
        "meeting": meeting,
        "action": action,
        "message": "Urgent counselor support requested" if (escalation or meeting or action) else "No active counselor support request"
    }

@app.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: int,
    token: str = Query(...),
    api_key: str = Query(...),
):
    """
    Real-time one-to-one chat endpoint.

    Local example:
    ws://192.168.1.170:8002/ws/chat/1?token=JWT&api_key=mobile_app_key_12345

    Production example:
    wss://recoverly-social.onrender.com/ws/chat/1?token=JWT&api_key=mobile_app_key_12345
    """

    if api_key != MOBILE_APP_CONFIG["api_key"]:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_id = get_user_id_from_ws_token(token)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        engine = get_engine()
        engine.assert_user_in_conversation(conversation_id, user_id)
    except Exception:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(conversation_id, user_id, websocket)

    await manager.send_to_user(
        conversation_id,
        user_id,
        {
            "event": "connected",
            "data": {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "message": "Live chat connected",
            },
        },
    )

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            if event == "ping":
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "pong",
                        "data": {
                            "timestamp": datetime.now().isoformat(),
                        },
                    },
                )
                continue

            if event != "send_message":
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "error",
                        "data": {
                            "message": "Unsupported WebSocket event",
                        },
                    },
                )
                continue

            text = (data.get("text") or "").strip()

            if not text:
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "error",
                        "data": {
                            "message": "Message text cannot be empty",
                        },
                    },
                )
                continue

            result = process_chat_message(
                conversation_id=conversation_id,
                user_id=user_id,
                text=text,
            )

            await manager.broadcast_to_conversation(
                conversation_id,
                {
                    "event": "new_message",
                    "data": result["message"],
                },
            )

            intervention = result.get("intervention")

            if intervention and intervention.get("type") != "NONE":
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "intervention",
                        "data": intervention,
                    },
                )

            counselor_support = result.get("counselor_support")

            if counselor_support:
                await manager.send_to_user(
                    conversation_id,
                    user_id,
                    {
                        "event": "counselor_support_update",
                        "data": counselor_support,
                    },
                )

    except WebSocketDisconnect:
        manager.disconnect(conversation_id, user_id, websocket)

    except Exception as e:
        logger.error(f"WebSocket chat error: {e}", exc_info=True)

        try:
            await manager.send_to_user(
                conversation_id,
                user_id,
                {
                    "event": "error",
                    "data": {
                        "message": str(e),
                    },
                },
            )
        except Exception:
            pass

        manager.disconnect(conversation_id, user_id, websocket)


# STARTUP/SHUTDOWN


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info(f"Agentic Support and Peer Network Facilitator")
    
    # Pre-load models 
    try:
        analyzer = get_analyzer()
        logger.info("ML models loaded")
    except Exception as e:
        logger.error(f"Failed to load models: {e}")
        raise
    
    # Test database connection
    try:
        engine = get_engine()
        logger.info("Database connected")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    logger.info("API is ready to receive requests")
    

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info(f"Shutting down {SERVICE_NAME}")
    
    # Close database connections
    try:
        engine = get_engine()
        engine.close()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")



# RUN SERVER


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "routes:app",
        host=API_CONFIG['host'],
        port=API_CONFIG['port'],
        reload=API_CONFIG['reload'],
        log_level="info"
    )