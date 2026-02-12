"""
FastAPI Server for Recoverly Risk Monitoring System
Handles incoming messages from the mobile app and returns risk assessments
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import logging

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import API_CONFIG, RECOVERLY_APP_CONFIG, LOGGING_CONFIG
from database.temporal_engine import TemporalRiskEngine, get_engine
from models.risk_analyzer import get_analyzer

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=LOGGING_CONFIG['level'],
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['log_file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Recoverly Risk Monitoring API",
    description="Backend system for real-time psychological risk detection in peer support conversations",
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

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class MessageRequest(BaseModel):
    """Request body for message analysis"""
    user_id: str = Field(..., description="Unique user identifier")
    message_text: str = Field(..., description="Message content", min_length=1)
    conversation_type: str = Field(default="buddy", description="'buddy' or 'counselor'")
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
    user_id: str
    predictions: MessagePrediction
    message_level_risk: str  # Not used for interventions, just FYI
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


class InterventionRecommendation(BaseModel):
    """Recommended intervention for a user"""
    user_id: str
    risk_label: str
    intervention_type: str
    message: str
    urgency: str
    context: dict


# ============================================================================
# AUTHENTICATION (Simple API Key)
# ============================================================================

async def verify_api_key(x_api_key: str = Header(...)):
    """
    Verify API key from mobile app
    In production: use proper authentication (JWT, OAuth2)
    """
    if x_api_key != RECOVERLY_APP_CONFIG['api_key']:
        logger.warning(f"Invalid API key attempt: {x_api_key}")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Recoverly Risk Monitoring API",
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
    
    This endpoint is called by the Recoverly mobile app whenever
    a user sends a message (to buddies or counselors)
    """
    try:
        logger.info(f"Analyzing message from user: {request.user_id}")
        
        # Get analyzer and engine
        analyzer = get_analyzer()
        engine = get_engine()
        
        # Run ML models
        predictions = analyzer.analyze_message(request.message_text)
        
        # Store in database
        message_id = engine.store_message_prediction(
            user_id=request.user_id,
            message_text=request.message_text,
            predictions=predictions,
            conversation_type=request.conversation_type,
            timestamp=request.timestamp
        )
        
        logger.info(f"Stored message {message_id} for user {request.user_id}")
        
        # Return results
        return MessageResponse(
            message_id=message_id,
            user_id=request.user_id,
            predictions=MessagePrediction(**predictions),
            message_level_risk="informational_only",  # Not used for decisions
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
    
    This triggers temporal aggregation and returns the user's
    current risk state based on all recent messages
    """
    try:
        logger.info(f"Computing risk profile for user: {user_id}")
        
        # Get engine and analyzer
        engine = get_engine()
        analyzer = get_analyzer()
        thresholds = analyzer.get_thresholds()
        
        # Compute risk profile
        profile = engine.update_user_risk_profile(user_id, thresholds)
        
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
        logger.info(f"Triggered risk check for user: {user_id}")
        
        # Get engine and analyzer
        engine = get_engine()
        analyzer = get_analyzer()
        thresholds = analyzer.get_thresholds()
        
        # Compute risk profile
        profile = engine.update_user_risk_profile(user_id, thresholds)
        
        # TODO (Week 2-3): Trigger intervention agent here
        # intervention_agent.process_user(profile)
        
        return {
            "user_id": user_id,
            "risk_label": profile['current_risk_label'],
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
            label = profile['risk_label']
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


# ============================================================================
# STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("=" * 80)
    logger.info("Starting Recoverly Risk Monitoring API")
    logger.info("=" * 80)
    
    # Pre-load models (ensures they're ready)
    try:
        analyzer = get_analyzer()
        logger.info("✓ ML models loaded")
    except Exception as e:
        logger.error(f"✗ Failed to load models: {e}")
        raise
    
    # Test database connection
    try:
        engine = get_engine()
        logger.info("✓ Database connected")
    except Exception as e:
        logger.error(f"✗ Failed to connect to database: {e}")
        raise
    
    logger.info("✓ API is ready to receive requests")
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Recoverly Risk Monitoring API")
    
    # Close database connections
    try:
        engine = get_engine()
        engine.close()
        logger.info("✓ Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=API_CONFIG['host'],
        port=API_CONFIG['port'],
        reload=API_CONFIG['reload'],
        log_level="info"
    )
