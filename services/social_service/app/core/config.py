"""
Configuration Management for Recoverly Risk Monitoring System
Loads settings from environment variables with fallback to defaults
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Connection parameters (for psycopg2.connect())
DB_CONN_PARAMS = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'recoverly_chatrisk'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
}

# Connection pool configuration (for production use)
DB_POOL_CONFIG = {
    **DB_CONN_PARAMS,  # Include all connection params
    'minconn': int(os.getenv('DB_MIN_CONN', 2)),
    'maxconn': int(os.getenv('DB_MAX_CONN', 10))
}

# Legacy: Keep DB_CONFIG for backward compatibility
DB_CONFIG = DB_CONN_PARAMS

# ============================================================================
# MODEL PATHS
# ============================================================================

MODELS_DIR = PROJECT_ROOT / "models"

RISK_MODEL_PATH = MODELS_DIR / "risk_classification" / "Risk_Classification_final"
ISOLATION_MODEL_PATH = MODELS_DIR / "isolation" / "isolation_model_final"

# Verify models exist
if not RISK_MODEL_PATH.exists():
    raise FileNotFoundError(f"Risk model not found at: {RISK_MODEL_PATH}")
if not ISOLATION_MODEL_PATH.exists():
    raise FileNotFoundError(f"Isolation model not found at: {ISOLATION_MODEL_PATH}")

# ============================================================================
# FUSION CONFIGURATION
# ============================================================================

FUSION_CONFIG_PATH = Path(__file__).parent / "fusion_v2.json"

if not FUSION_CONFIG_PATH.exists():
    raise FileNotFoundError(f"Fusion config not found at: {FUSION_CONFIG_PATH}")

# ============================================================================
# API CONFIGURATION
# ============================================================================

API_CONFIG = {
    'host': os.getenv('API_HOST', '0.0.0.0'),
    'port': int(os.getenv('API_PORT', 8000)),
    'reload': os.getenv('API_RELOAD', 'true').lower() == 'true',
    'workers': int(os.getenv('API_WORKERS', 1))
}

# ============================================================================
# RISK MONITORING SETTINGS
# ============================================================================

RISK_SETTINGS = {
    # Time windows for aggregation
    'short_window_days': 7,
    'medium_window_days': 30,
    
    # Check-in settings
    'silent_user_days': 3,  # Days of no buddy messages = needs check-in
    
    # Intervention frequency limits
    'max_nudges_per_day': 2,
    'min_hours_between_nudges': 12,
    
    # Risk label mappings
    'risk_labels': {
        0: 'CRAVING',
        1: 'NEGATIVE_MOOD',
        2: 'NEUTRAL',
        3: 'RELAPSE',
        4: 'TOXIC'
    }
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'log_file': PROJECT_ROOT / 'logs' / 'risk_engine.log'
}

# Create logs directory if it doesn't exist
LOGGING_CONFIG['log_file'].parent.mkdir(exist_ok=True)

# ============================================================================
# MOBILE APP INTEGRATION (for Week 6+)
# ============================================================================

RECOVERLY_APP_CONFIG = {
    'api_key': os.getenv('RECOVERLY_API_KEY', 'dev_key_12345'),  # Set in production
    'webhook_secret': os.getenv('WEBHOOK_SECRET', 'change_me_in_production'),
    'callback_url': os.getenv('CALLBACK_URL', 'https://api.recoverly.app/v1/interventions')
}

# ============================================================================
# DEVELOPMENT vs PRODUCTION
# ============================================================================

ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
IS_PRODUCTION = ENVIRONMENT == 'production'
IS_DEVELOPMENT = ENVIRONMENT == 'development'

if IS_PRODUCTION:
    # Production-specific settings
    API_CONFIG['reload'] = False
    API_CONFIG['workers'] = 4
    LOGGING_CONFIG['level'] = 'WARNING'

print(f"✓ Configuration loaded for environment: {ENVIRONMENT}")