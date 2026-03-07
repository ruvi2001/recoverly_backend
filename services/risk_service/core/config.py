import os
from pathlib import Path
from dotenv import load_dotenv

# core/config.py is at:
# recoverly_backend/services/risk_service/core/config.py
BACKEND_ROOT = Path(__file__).resolve().parents[3]  # -> recoverly_backend/
ENV_PATH = BACKEND_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
    print(f"✓ [risk_service] Loaded env from: {ENV_PATH}")
else:
    load_dotenv()  # fallback
    print(f"[risk_service] .env NOT found at: {ENV_PATH} (loaded from current env instead)")

DB_HOST = os.getenv("DB_HOST", "localhost").strip()
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "recoverly_platform").strip()
DB_USER = os.getenv("DB_USER", "postgres").strip()
DB_PASSWORD = os.getenv("DB_PASSWORD", "piumi1234")

# Debug (safe)
print(f"✓ [risk_service] DB_HOST={DB_HOST} DB_PORT={DB_PORT} DB_NAME={DB_NAME} DB_USER={DB_USER}")
print(f"✓ [risk_service] DB_PASSWORD loaded? {'YES' if DB_PASSWORD else 'NO'}")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

RISK_SERVICE_PORT = int(os.getenv("RISK_SERVICE_PORT", "8001"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip()

# model folder is inside this service
MODEL_DIR = Path(__file__).resolve().parents[1] / "model"
MODEL_PATH = MODEL_DIR / "Relapse_Risk_Estimation_Model_final.pkl"
SCALER_PATH = MODEL_DIR / "Relapse_Risk_Estimation_scaler.pkl"
EXPLAINER_PATH = MODEL_DIR / "Relapse_Risk_Estimation_shap_explainer.pkl"