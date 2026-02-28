"""
FastAPI Server for Recoverly Risk Monitoring System
Handles incoming messages from the mobile app and returns risk assessments
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from agent.intervention_agent import get_agent
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.config import API_CONFIG, MOBILE_APP_CONFIG, LOGGING_CONFIG, SERVICE_NAME
from db.temporal_engine import TemporalRiskEngine, get_engine
from ml.risk_analyzer import get_analyzer


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


# class InterventionRecommendation(BaseModel):
#     """Recommended intervention for a user"""
#     user_id: str
#     risk_label: str
#     intervention_type: str
#     message: str
#     urgency: str
#     context: dict

# AUTHENTICATION (Simple API Key)


async def verify_api_key(x_api_key: str = Header(...)):
    """
    Verify API key from mobile app
    In production: use proper authentication (JWT, OAuth2)
    """
    if x_api_key != MOBILE_APP_CONFIG['api_key']:
        logger.warning(f"Invalid API key attempt: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def get_user_id(x_user_id: str = Header(..., alias="X-User-Id")):
    return x_user_id

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

        # AUTO-TRIGGER RISK CHECK (if message has high risk)
        if predictions['risk_score'] > 0.7:  # Threshold
            logger.info(f"High-risk message detected - triggering intervention check")
            
            # Update risk profile
            profile = engine.update_user_risk_profile(request.user_id, thresholds)
            
            # Trigger agent
            agent = get_agent(engine)
            actions = agent.process_user(profile)
            
            logger.info(f"Auto-triggered {len(actions)} interventions")
        
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

@app.post("/chat/conversations/one-to-one")
async def create_or_get_one_to_one(
    body: OneToOneConversationRequest,
    user_id: str = Depends(get_user_id),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    engine.ensure_user_exists(user_id)
    engine.ensure_user_exists(body.other_user_id)

    cid = engine.get_or_create_one_to_one_conversation(user_id, body.other_user_id, body.conversation_type)
    return {"conversation_id": cid}


@app.get("/chat/conversations")
async def list_my_conversations(
    user_id: str = Depends(get_user_id),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    return {"conversations": engine.list_conversations_for_user(user_id)}


@app.get("/chat/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: int,
    limit: int = 50,
    user_id: str = Depends(get_user_id),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    engine.assert_user_in_conversation(conversation_id, user_id)
    return {"messages": engine.get_messages(conversation_id, limit)}


@app.post("/chat/conversations/{conversation_id}/messages")
async def send_message_rest(
    conversation_id: int,
    body: SendChatMessageRequest,
    user_id: str = Depends(get_user_id),
    api_key: str = Depends(verify_api_key)
):
    engine = get_engine()
    engine.assert_user_in_conversation(conversation_id, user_id)

    recipient_id = engine.get_other_participant(conversation_id, user_id)

    analyzer = get_analyzer()
    predictions = analyzer.analyze_message(body.text)

    # IMPORTANT: set conversation_type from DB (recommended)
    # For MVP, you can pass "buddy" and later fix.
    conversation_type = "buddy"

    message_id, prediction_id = engine.store_message_with_prediction(
        user_id=user_id,
        message_text=body.text,
        predictions=predictions,
        conversation_type=conversation_type,
        recipient_id=recipient_id,
        conversation_id=conversation_id
    )

    # profile + intervention logic (your existing)
    thresholds = analyzer.get_thresholds()
    profile = engine.update_user_risk_profile(user_id, thresholds)
    if predictions["risk_score"] > 0.7:
        agent = get_agent(engine)
        agent.process_user(profile)

    return {"message_id": message_id, "prediction_id": prediction_id}

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
