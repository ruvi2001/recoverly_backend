import os
from pathlib import Path
from dotenv import load_dotenv

# core/config.py is at:
# recoverly_backend/services/reco_service/core/config.py
BACKEND_ROOT = Path(__file__).resolve().parents[3]  # -> recoverly_backend/
ENV_PATH = BACKEND_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
    print(f"✓ [reco_service] Loaded env from: {ENV_PATH}")
else:
    load_dotenv()  # fallback
    print(f"[reco_service] .env NOT found at: {ENV_PATH} (loaded from current env instead)")

DB_HOST = os.getenv("DB_HOST", "localhost").strip()
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "recoverly_platform").strip()
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

print(f"✓ [reco_service] DB_HOST={DB_HOST} DB_PORT={DB_PORT} DB_NAME={DB_NAME} DB_USER={DB_USER}")
print(f"✓ [reco_service] DB_PASSWORD loaded? {'YES' if DB_PASSWORD else 'NO'}")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

RECO_SERVICE_PORT = int(os.getenv("RECO_SERVICE_PORT", "8003"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip()

# artifacts folder inside this service
ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "ml" / "artifacts"

# prefer pkl because that matches your uploaded classifier bundle
CLASSIFIER_PATH = ARTIFACT_DIR / "arrs_classifier_bundle.pkl"
CLASSIFIER_JOBLIB_PATH = ARTIFACT_DIR / "arrs_classifier_bundle.joblib"
BANDIT_RUNTIME_PATH = ARTIFACT_DIR / "arrs_bandit_runtime.pkl"
ENCODING_SCHEMA_PATH = ARTIFACT_DIR / "arrs_encoding_schema.json"
POLICY_CONFIG_PATH = ARTIFACT_DIR / "arrs_policy_config.json"
ACTIONS_METADATA_PATH = ARTIFACT_DIR / "arrs_actions_metadata.json"

RECO_SCHEMA = "reco"

print(f"✓ [reco_service] ARTIFACT_DIR={ARTIFACT_DIR}")