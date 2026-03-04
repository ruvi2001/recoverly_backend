import asyncio
import pickle
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any

from core.config import MODEL_PATH, SCALER_PATH, EXPLAINER_PATH as SHAP_EXPLAINER_PATH

logger = logging.getLogger(__name__)

QUESTIONNAIRE_FEATURES = [
    "self_efficacy_doubt", "emotional_distress", "anger_irritability",
    "unclear_thinking", "poor_concentration", "feeling_trapped",
    "sleep_disturbance", "craving_thoughts", "relapse_ideation",
    "recovery_actions",
]

MODEL_VERSION = "Relapse_Risk_Estimation_Model_final"
LOW_MAX, MOD_MAX, HIGH_MAX = 15.0, 50.0, 85.0

def categorize_risk(risk_percent: float) -> tuple[str, str]:
    if risk_percent >= HIGH_MAX:
        return "VERY HIGH RISK", "🔴"
    if risk_percent >= MOD_MAX:
        return "HIGH RISK", "🟠"
    if risk_percent >= LOW_MAX:
        return "MODERATE RISK", "🟡"
    return "LOW RISK", "🟢"

class RiskAnalyzer:
    def __init__(self):
        with open(MODEL_PATH, "rb") as f:
            self.model = pickle.load(f)["model"]
        with open(SCALER_PATH, "rb") as f:
            self.scaler = pickle.load(f)
        with open(SHAP_EXPLAINER_PATH, "rb") as f:
            self.explainer = pickle.load(f)

        logger.info("✓ ML models loaded")

    @staticmethod
    def _preprocess_answers(answers: Dict[str, int]) -> Dict[str, int]:
        processed = answers.copy()
        if processed.get("recovery_actions") is not None:
            processed["recovery_actions"] = 8 - int(processed["recovery_actions"])
        return processed

    def _run_inference(self, answers: Dict[str, int]) -> Dict[str, Any]:
        processed = self._preprocess_answers(answers)

        X = pd.DataFrame([[processed[f] for f in QUESTIONNAIRE_FEATURES]], columns=QUESTIONNAIRE_FEATURES)
        scaled = pd.DataFrame(self.scaler.transform(X), columns=QUESTIONNAIRE_FEATURES)

        proba = self.model.predict_proba(scaled)[0]
        risk_percent = float(proba[1] * 100.0)

        category, emoji = categorize_risk(risk_percent)

        # SHAP can fail if explainer mismatch; keep safe
        xai: List[Dict[str, Any]] = []
        try:
            vals = self.explainer.shap_values(scaled)
            if isinstance(vals, list):
                vals = vals[1][0]
            else:
                vals = np.array(vals)
                vals = vals[0, :, 1] if vals.ndim == 3 else vals[0]

            df = pd.DataFrame({
                "feature_name": QUESTIONNAIRE_FEATURES,
                "feature_value": [int(processed[f]) for f in QUESTIONNAIRE_FEATURES],
                "contribution": np.array(vals).astype(float),
            })
            df["rank"] = df["contribution"].abs().rank(ascending=False, method="min").astype(int)
            df = df.sort_values("rank")
            xai = df.to_dict(orient="records")
        except Exception as e:
            logger.warning("SHAP failed: %s", e)

        return {
            "predicted_label": int(proba[1] >= 0.5),
            "predicted_risk_percent": round(risk_percent, 2),
            "category": category,
            "emoji": emoji,
            "total_score": int(sum(int(processed[f]) for f in QUESTIONNAIRE_FEATURES)),
            "model_version": MODEL_VERSION,
            "xai": xai,
        }

    async def predict(self, answers: Dict[str, int]) -> Dict[str, Any]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_inference, answers)

_instance: RiskAnalyzer | None = None

def init_analyzer() -> None:
    global _instance
    if _instance is None:
        _instance = RiskAnalyzer()
        logger.info("✓ RiskAnalyzer initialised")

def get_analyzer() -> RiskAnalyzer:
    if _instance is None:
        raise RuntimeError("RiskAnalyzer not initialised. Call init_analyzer() on startup.")
    return _instance