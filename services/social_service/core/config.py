"""
Configuration Management for Social Service
Agentic Support and Peer Network Facilitator

"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()    # social_service/
BACKEND_ROOT = PROJECT_ROOT.parent.parent                 # recoverly_backend/

# Check if models exist in parent backend directory
MODELS_DIR = BACKEND_ROOT / "models"

if not MODELS_DIR.exists():
    MODELS_DIR = BACKEND_ROOT.parent / "models"

print(f"Looking for models at: {MODELS_DIR}")


# MICROSERVICE IDENTIFICATION

SERVICE_NAME = "social_service"
SERVICE_VERSION = "1.0.0"
SERVICE_PORT = int(os.getenv('SERVICE_PORT', 8002))  # Each microservice has unique port


# DATABASE CONFIGURATION (SHARED DATABASE, ISOLATED SCHEMA)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'recoverly_platform'),  # SHARED across all services
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),  # CHANGE IN .ENV!
    'min_conn': int(os.getenv('DB_MIN_CONN', 2)),
    'max_conn': int(os.getenv('DB_MAX_CONN', 10)),
    'options': '-c search_path=social,core'  # Access ONLY social schema + shared core schema
}

# Schema names
SOCIAL_SCHEMA = 'social'
CORE_SCHEMA = 'core'  # For shared tables like users, sessions

# MODEL PATHS
# PARENT_DIR = PROJECT_ROOT.parent
# MODELS_DIR = PARENT_DIR / "models" if (PARENT_DIR / "models").exists() else PROJECT_ROOT.parent / "models"


RISK_MODEL_PATH = MODELS_DIR / "risk_classification" / "Risk_Classification_final"
ISOLATION_MODEL_PATH = MODELS_DIR / "isolation" / "isolation_model_final"

# Verify models exist
if not RISK_MODEL_PATH.exists():
    import warnings
    warnings.warn(f"Risk model not found at: {RISK_MODEL_PATH}")
if not ISOLATION_MODEL_PATH.exists():
    import warnings
    warnings.warn(f"Isolation model not found at: {ISOLATION_MODEL_PATH}")



# FUSION CONFIGURATION

FUSION_CONFIG_PATH = PROJECT_ROOT / "ml" / "fusion_v2.json"

if not FUSION_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Fusion config not found at: {FUSION_CONFIG_PATH}")

# API CONFIGURATION

API_CONFIG = {
    'host': os.getenv('API_HOST', '0.0.0.0'),
    'port': SERVICE_PORT,
    'reload': os.getenv('API_RELOAD', 'true').lower() == 'true',
    'workers': int(os.getenv('API_WORKERS', 1))
}

# MICROSERVICE COMMUNICATION

# URLs for other microservices (for inter-service communication)
RISK_SERVICE_URL = os.getenv('RISK_SERVICE_URL', 'http://localhost:8000')
RECO_SERVICE_URL = os.getenv('RECO_SERVICE_URL', 'http://localhost:8001')
CAUSAL_SERVICE_URL = os.getenv('CAUSAL_SERVICE_URL', 'http://localhost:8003')

# API Keys for inter-service authentication
INTERNAL_API_KEY = os.getenv('INTERNAL_API_KEY', 'internal_service_key_change_me')
EXTERNAL_API_KEY = os.getenv('EXTERNAL_API_KEY', 'mobile_app_key_change_me')

# RISK MONITORING SETTINGS

RISK_SETTINGS = {
    # Time windows for aggregation
    'short_window_days': 7,
    'medium_window_days': 30,
    
    # Check-in settings
    'silent_user_days': 3,  # Days of no buddy messages = needs check-in
    
    # Intervention frequency limits
    'max_nudges_per_day': 2,
    'min_hours_between_nudges': 12,
    
    # Risk label mappings (from your ML models)
    'risk_labels': {
        0: 'CRAVING',
        1: 'NEGATIVE_MOOD',
        2: 'NEUTRAL',
        3: 'RELAPSE',
        4: 'TOXIC'
    },
    
    # Final risk decision labels
    'final_risk_labels': ['HIGH_RISK', 'MODERATE_RISK', 'LOW_RISK', 'ISOLATION_ONLY']
}

# INTERVENTION SETTINGS

INTERVENTION_CONFIG = {
    # Action mappings for each risk level
    'actions_by_risk_level': {
        'HIGH_RISK': [
            'schedule_counselor_meeting',
            'request_family_notification',
            'provide_crisis_resources'
        ],
        'MODERATE_RISK': [
            'send_buddy_connection_nudge',
            'send_counselor_encouragement',
            'recommend_coping_exercises'
        ],
        'LOW_RISK': [
            'send_positive_reinforcement'
        ],
        'ISOLATION_ONLY': [
            'send_buddy_suggestion',
            'recommend_group_activity'
        ]
    },
    
    # Nudge templates directory
    'templates_path': PROJECT_ROOT / 'templates' / 'nudges',
    
    # Max interventions per user per day
    'max_interventions_per_day': 3
}

# LOGGING CONFIGURATION

LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s',
    'log_file': PROJECT_ROOT / 'logs' / f'{SERVICE_NAME}.log'
}

# Create logs directory if it doesn't exist
LOGGING_CONFIG['log_file'].parent.mkdir(exist_ok=True)

# MOBILE APP INTEGRATION

MOBILE_APP_CONFIG = {
    'api_key': os.getenv('MOBILE_APP_API_KEY', 'mobile_app_key_12345'),
    'webhook_url': os.getenv('MOBILE_APP_WEBHOOK_URL', 'https://api.recoverly.app/v1/notifications'),
    'push_notification_service': os.getenv('PUSH_SERVICE', 'firebase')  # or 'onesignal'
}

# ENVIRONMENT

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
IS_PRODUCTION = ENVIRONMENT == 'production'
IS_DEVELOPMENT = ENVIRONMENT == 'development'

if IS_PRODUCTION:
    # Production-specific settings
    API_CONFIG['reload'] = False
    API_CONFIG['workers'] = 4
    LOGGING_CONFIG['level'] = 'WARNING'


# AGENT CONFIGURATION

AGENT_CONFIG = {
    'enabled': os.getenv('AGENT_ENABLED', 'false').lower() == 'true',
    'llm_provider': os.getenv('LLM_PROVIDER', 'openai'),  # 'openai' or 'anthropic'
    'llm_api_key': os.getenv('LLM_API_KEY', ''),
    'llm_model': os.getenv('LLM_MODEL', 'gpt-4'),
    'temperature': float(os.getenv('LLM_TEMPERATURE', 0.3)),
    'max_tokens': int(os.getenv('LLM_MAX_TOKENS', 1000))
}

print(f"✓ {SERVICE_NAME} configuration loaded for environment: {ENVIRONMENT}")
print(f"  Database: {DB_CONFIG['database']}")
print(f"  Schema: {SOCIAL_SCHEMA}")
print(f"  Port: {SERVICE_PORT}")