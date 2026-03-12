from pathlib import Path
import json
import joblib
import numpy as np

from ml.encoder import get_encoder
from ml.bandit import get_bandit_runtime
from services.risk_service.engine.monitoring_engine import risk_level

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BASE_DIR / "ml" / "artifacts"

CLASSIFIER_BUNDLE_PATH = ARTIFACTS_DIR / "arrs_classifier_bundle.joblib"
RECOMMENDATION_LIBRARY_PATH = ARTIFACTS_DIR / "recommendation_library.json"
ACTIONS_METADATA_PATH = ARTIFACTS_DIR / "arrs_actions_metadata.json"

_CLASSIFIER_BUNDLE = None
_RECOMMENDATION_LIBRARY = None
_ACTIONS_METADATA = None


def first_or_empty(values):
    if isinstance(values, list) and values:
        return values[0]
    return ""


def load_assets():
    global _CLASSIFIER_BUNDLE, _RECOMMENDATION_LIBRARY, _ACTIONS_METADATA

    if _CLASSIFIER_BUNDLE is None:
        _CLASSIFIER_BUNDLE = joblib.load(CLASSIFIER_BUNDLE_PATH)

    if _RECOMMENDATION_LIBRARY is None:
        with open(RECOMMENDATION_LIBRARY_PATH, "r", encoding="utf-8") as f:
            _RECOMMENDATION_LIBRARY = json.load(f)

    if _ACTIONS_METADATA is None:
        with open(ACTIONS_METADATA_PATH, "r", encoding="utf-8") as f:
            _ACTIONS_METADATA = json.load(f)

    return _CLASSIFIER_BUNDLE, _RECOMMENDATION_LIBRARY, _ACTIONS_METADATA


def map_frontend_answers_to_encoder_payload(answers: dict, relapse_risk_level: str = ""):
    return {
        "risk_level": risk_level,

        "support_people": answers.get("q1", []),
        "support_contact_freq": first_or_empty(answers.get("q2")),
        "first_contact": first_or_empty(answers.get("q3")),
        "coping_choices": answers.get("q4", []),
        "best_coping": first_or_empty(answers.get("q5")),
        "coping_efficacy": first_or_empty(answers.get("q6")),

        "sp_helpfulness": first_or_empty(answers.get("q7")),
        "sp_frequency": first_or_empty(answers.get("q8")),

        "motivations": [first_or_empty(answers.get("q9"))] if answers.get("q9") else [],
        "triggers": answers.get("q10", []),
        "peak_urge_time": first_or_empty(answers.get("q11")),
        "locations": answers.get("q12", []),

        "companion": first_or_empty(answers.get("q13")),
        "exposure": first_or_empty(answers.get("q14")),
        "invite_response": first_or_empty(answers.get("q15")),

        "positive_steps": answers.get("q16", []),
        "readiness": first_or_empty(answers.get("q17")),
        "support_needed": first_or_empty(answers.get("q18")),
    }


def extract_classifier_parts(bundle):
    """
    You may need to adjust this depending on how arrs_classifier_bundle.joblib was saved.
    """
    if isinstance(bundle, dict):
        if "model" in bundle:
            model = bundle["model"]
        elif "classifier" in bundle:
            model = bundle["classifier"]
        else:
            raise ValueError("No model/classifier found in arrs_classifier_bundle.joblib")

        label_encoder = bundle.get("label_encoder")
        return model, label_encoder

    raise ValueError("Unexpected classifier bundle format")


def get_allowed_actions_for_family(predicted_family: str, actions_metadata: dict) -> list[str]:
    """
    Adjust this if your metadata uses a different shape.
    """
    family_action_map = actions_metadata.get("family_action_map", {})
    allowed = family_action_map.get(predicted_family, [])

    if allowed:
        return allowed

    # fallback: all actions
    return list(actions_metadata.get("actions", []))


def get_recommendation_for_action(action: str, recommendation_library: dict):
    """
    Adjust if recommendation_library.json uses a different structure.
    """
    return recommendation_library.get(action, recommendation_library.get("default", {}))


def run_arrs_analysis(answers: dict, relapse_risk_level: str = "", submitted_at: str | None = None):
    bundle, recommendation_library, actions_metadata = load_assets()

    encoder = get_encoder()
    payload = map_frontend_answers_to_encoder_payload(
        answers=answers,
        relapse_risk_level=relapse_risk_level,
    )

    encoded = encoder.encode(payload)
    vector = encoder.vector(encoded)
    x = np.asarray(vector, dtype=float).reshape(1, -1)

    model, label_encoder = extract_classifier_parts(bundle)

    pred_raw = model.predict(x)[0]

    if label_encoder is not None:
        predicted_family = label_encoder.inverse_transform([pred_raw])[0]
    else:
        predicted_family = str(pred_raw)

    confidence = None
    family_scores = None

    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(x)[0]
        confidence = float(np.max(probs))

        if label_encoder is not None:
            labels = label_encoder.classes_
            family_scores = {
                str(label): float(score)
                for label, score in zip(labels, probs)
            }

    allowed_actions = get_allowed_actions_for_family(predicted_family, actions_metadata)

    bandit = get_bandit_runtime()
    selected_action, bandit_scores = bandit.choose(
        feature_vector=vector,
        allowed_actions=allowed_actions,
    )

    recommendation = get_recommendation_for_action(
        selected_action,
        recommendation_library,
    )

    return {
        "predicted_family": predicted_family,
        "selected_action": selected_action,
        "confidence": confidence,
        "family_scores": family_scores,
        "bandit_scores": bandit_scores,
        "recommendation": recommendation,
    }