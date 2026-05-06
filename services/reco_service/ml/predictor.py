from pathlib import Path
import joblib
import json

BASE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = BASE_DIR / "artifacts"

MODEL_BUNDLE_PATH = ARTIFACTS_DIR / "arrs_classifier_bundle.joblib"
LIBRARY_PATH = ARTIFACTS_DIR / "recommendation_library.json"

_bundle = None
_recommendation_library = None


def load_artifacts():
    global _bundle, _recommendation_library

    if _bundle is None:
        _bundle = joblib.load(MODEL_BUNDLE_PATH)

    if _recommendation_library is None:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            _recommendation_library = json.load(f)

    return _bundle, _recommendation_library


def first_or_empty(values):
    if isinstance(values, list) and values:
        return values[0]
    return ""


def map_answers_to_encoder_payload(answers: dict, risk_level: str = "Moderate"):
    return {
        "relapse_risk_level": risk_level,
        "support_people": answers.get("q1", []),
        "support_contact_freq": first_or_empty(answers.get("q2")),
        "first_contact": first_or_empty(answers.get("q3")),
        "coping_choices": answers.get("q4", []),
        "best_coping": first_or_empty(answers.get("q5")),
        "coping_efficacy": first_or_empty(answers.get("q6")),
        "sp_helpfulness": first_or_empty(answers.get("q7")),
        "sp_frequency": first_or_empty(answers.get("q8")),
        "motivations": answers.get("q9", []),
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


def predict_arrs(answers: dict, risk_level: str = "Moderate"):
    bundle, recommendation_library = load_artifacts()

    from ml.encoder import get_encoder
    encoder = get_encoder()

    classifier = bundle.get("classifier") or bundle.get("model")
    if classifier is None:
        raise ValueError(
            f"No classifier/model found in bundle. Keys: {list(bundle.keys()) if isinstance(bundle, dict) else type(bundle)}"
        )

    label_encoder = bundle.get("label_encoder")

    payload = map_answers_to_encoder_payload(answers, risk_level=risk_level)
    print("ENCODER PAYLOAD:", payload)

    encoded_features = encoder.encode(payload)
    print("ENCODED FEATURES:", encoded_features)

    feature_vector = encoder.vector(encoded_features)
    print("FEATURE VECTOR:", feature_vector)

    X = [feature_vector]

    pred_idx = classifier.predict(X)[0]

    if label_encoder is not None:
        predicted_family = label_encoder.inverse_transform([pred_idx])[0]
    else:
        predicted_family = str(pred_idx)

    confidence = None
    if hasattr(classifier, "predict_proba"):
        proba = classifier.predict_proba(X)[0]
        confidence = float(max(proba))

    recommended_action = recommendation_library.get(
        predicted_family,
        "No recommendation found for this category."
    )

    return {
        "predicted_family": predicted_family,
        "selected_action": recommended_action,
        "recommendation": recommended_action,
        "confidence": confidence,
    }