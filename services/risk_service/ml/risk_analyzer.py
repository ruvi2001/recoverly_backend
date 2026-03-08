import asyncio
import pickle
import logging
import numpy as np
import pandas as pd
import shap
from typing import Dict, List, Any

from core.config import MODEL_PATH, SCALER_PATH

logger = logging.getLogger(__name__)

QUESTIONNAIRE_FEATURES = [
    "self_efficacy_doubt",
    "emotional_distress",
    "anger_irritability",
    "unclear_thinking",
    "poor_concentration",
    "feeling_trapped",
    "sleep_disturbance",
    "craving_thoughts",
    "relapse_ideation",
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
        self.model = None
        self.scaler = None
        self.explainer = None

        self._load_model_and_scaler()
        self._build_explainer()

        logger.info("✓ ML model and scaler loaded")

    def _load_model_and_scaler(self) -> None:
        with open(MODEL_PATH, "rb") as f:
            loaded = pickle.load(f)

        # Supports either:
        # 1. {"model": trained_model, ...}
        # 2. direct model object
        if isinstance(loaded, dict) and "model" in loaded:
            self.model = loaded["model"]
        else:
            self.model = loaded

        with open(SCALER_PATH, "rb") as f:
            self.scaler = pickle.load(f)

    def _get_estimator_for_shap(self):
        estimator = self.model

        # If model is a sklearn Pipeline, try common final-step names
        if hasattr(estimator, "named_steps"):
            for step_name in ["classifier", "model", "rf", "random_forest", "estimator"]:
                if step_name in estimator.named_steps:
                    return estimator.named_steps[step_name]

            # fallback: last pipeline step
            try:
                return list(estimator.named_steps.values())[-1]
            except Exception:
                pass

        return estimator

    def _build_explainer(self) -> None:
        try:
            estimator = self._get_estimator_for_shap()
            self.explainer = shap.TreeExplainer(estimator)
            logger.info("✓ SHAP explainer rebuilt from model")
        except Exception as e:
            self.explainer = None
            logger.warning("SHAP explainer could not be created: %s", e)

    @staticmethod
    def _preprocess_answers(answers: Dict[str, int]) -> Dict[str, int]:
        processed = answers.copy()
        if processed.get("recovery_actions") is not None:
            processed["recovery_actions"] = 8 - int(processed["recovery_actions"])
        return processed

    def _run_inference(self, answers: Dict[str, int]) -> Dict[str, Any]:
        processed = self._preprocess_answers(answers)

        X = pd.DataFrame(
            [[processed[f] for f in QUESTIONNAIRE_FEATURES]],
            columns=QUESTIONNAIRE_FEATURES,
        )

        scaled = pd.DataFrame(
            self.scaler.transform(X),
            columns=QUESTIONNAIRE_FEATURES,
        )

        proba = self.model.predict_proba(scaled)[0]
        risk_percent = float(proba[1] * 100.0)

        category, emoji = categorize_risk(risk_percent)

        xai: List[Dict[str, Any]] = []
        try:
            if self.explainer is not None:
                vals = self.explainer.shap_values(scaled)

                if isinstance(vals, list):
                    vals = vals[1][0]
                else:
                    vals = np.array(vals)
                    vals = vals[0, :, 1] if vals.ndim == 3 else vals[0]

                df = pd.DataFrame(
                    {
                        "feature_name": QUESTIONNAIRE_FEATURES,
                        "feature_value": [int(processed[f]) for f in QUESTIONNAIRE_FEATURES],
                        "contribution": np.array(vals).astype(float),
                    }
                )
                df["rank"] = (
                    df["contribution"]
                    .abs()
                    .rank(ascending=False, method="min")
                    .astype(int)
                )
                df = df.sort_values("rank")
                xai = df.to_dict(orient="records")
        except Exception as e:
            logger.warning("SHAP failed during inference: %s", e)

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