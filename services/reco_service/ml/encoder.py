from typing import Any

import json
from pathlib import Path


_ENCODER = None


def norm_text(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def normalize_key(x: str) -> str:
    return norm_text(x).lower().replace("-", "_").replace(" ", "_")


def safe_name(x: str) -> str:
    return (
        str(x)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        .replace("'", "_")
        .replace("(", "")
        .replace(")", "")
        .replace(",", "")
    )


def split_multiselect(x: Any) -> list[str]:
    if x is None:
        return []

    if isinstance(x, list):
        return [normalize_key(v) for v in x if norm_text(v)]

    text = norm_text(x)
    if not text:
        return []

    return [normalize_key(part) for part in text.split(",") if norm_text(part)]


class RuntimeEncoder:
    def __init__(self, schema: dict):
        self.schema = schema
        self.feature_cols: list[str] = schema["FEATURE_COLS"]
        self.feature_fingerprint: str = schema["FEATURE_FINGERPRINT"]
        self.risk_map = {normalize_key(k): v for k, v in schema["RISK_MAP"].items()}

    def encode(self, payload: dict[str, Any]) -> dict[str, float]:
        """
        Encode normalized ARRS payload into the exact feature vector expected
        by the classifier bundle.

        Expected normalized payload keys:
        - relapse_risk_level
        - support_contact_freq
        - coping_efficacy
        - sp_helpfulness
        - sp_frequency
        - peak_urge_time
        - exposure
        - invite_response
        - readiness
        - first_contact
        - best_coping
        - companion
        - support_needed
        - support_people
        - coping_choices
        - motivations
        - triggers
        - locations
        - positive_steps
        """

        encoded: dict[str, float] = {col: 0.0 for col in self.feature_cols}

        # ---------------------------------------------------------
        # risk level
        # ---------------------------------------------------------
        risk_key = normalize_key(payload.get("relapse_risk_level", ""))
        encoded["risk_level_code"] = float(self.risk_map.get(risk_key, 0.0))

        # ---------------------------------------------------------
        # ordinal / categorical codes
        # ---------------------------------------------------------
        encoded["support_contact_freq_code"] = self._ordinal_encode(
            payload.get("support_contact_freq"),
            self.schema["FREQ_ORDER"],
        )
        encoded["coping_efficacy_code"] = self._ordinal_encode(
            payload.get("coping_efficacy"),
            self.schema["EFFICACY_ORDER"],
        )
        encoded["sp_helpfulness_code"] = self._ordinal_encode(
            payload.get("sp_helpfulness"),
            self.schema["SP_HELP_ORDER"],
        )
        encoded["sp_frequency_code"] = self._ordinal_encode(
            payload.get("sp_frequency"),
            self.schema["SP_FREQ_ORDER"],
        )
        encoded["peak_urge_time_code"] = self._ordinal_encode(
            payload.get("peak_urge_time"),
            self.schema["URGE_TIME_ORDER"],
        )
        encoded["exposure_code"] = self._ordinal_encode(
            payload.get("exposure"),
            self.schema["EXPOSURE_ORDER"],
        )
        encoded["invite_response_code"] = self._ordinal_encode(
            payload.get("invite_response"),
            self.schema["INVITE_ORDER"],
        )
        encoded["readiness_code"] = self._ordinal_encode(
            payload.get("readiness"),
            self.schema["READINESS_ORDER"],
        )

        encoded["first_contact_code"] = self._categorical_encode(
            payload.get("first_contact"),
            self.schema["FIRST_CONTACT"],
        )
        encoded["best_coping_code"] = self._categorical_encode(
            payload.get("best_coping"),
            self.schema["BEST_COPING"],
        )
        encoded["companion_code"] = self._categorical_encode(
            payload.get("companion"),
            self.schema["COMPANIONS"],
        )
        encoded["support_needed_code"] = self._categorical_encode(
            payload.get("support_needed"),
            self.schema["SUPPORT_NEEDED"],
        )

        # ---------------------------------------------------------
        # multi-hot groups
        # ---------------------------------------------------------
        self._multihot(
            encoded,
            payload.get("support_people", []),
            self.schema["SUPPORT_PEOPLE"],
            "support_",
        )
        self._multihot(
            encoded,
            payload.get("coping_choices", []),
            self.schema["COPING_CHOICES"],
            "coping_",
        )
        self._multihot(
            encoded,
            payload.get("motivations", []),
            self.schema["MOTIVATIONS"],
            "motivation_",
        )
        self._multihot(
            encoded,
            payload.get("triggers", []),
            self.schema["TRIGGERS"],
            "trigger_",
        )
        self._multihot(
            encoded,
            payload.get("locations", []),
            self.schema["LOCATIONS"],
            "location_",
        )
        self._multihot(
            encoded,
            payload.get("positive_steps", []),
            self.schema["POSITIVE_STEPS"],
            "positive_",
        )

        return encoded

    def vector(self, encoded: dict[str, float]) -> list[float]:
        return [float(encoded.get(col, 0.0)) for col in self.feature_cols]

    def _ordinal_encode(self, value: Any, order_list: list[str]) -> float:
        mapping = {normalize_key(k): i for i, k in enumerate(order_list)}
        return float(mapping.get(normalize_key(value), 0.0))

    def _categorical_encode(self, value: Any, allowed_list: list[str]) -> float:
        mapping = {normalize_key(k): i for i, k in enumerate(allowed_list)}
        return float(mapping.get(normalize_key(value), 0.0))

    def _multihot(
        self,
        encoded: dict[str, float],
        values: Any,
        allowed_list: list[str],
        prefix: str,
    ) -> None:
        parsed = set(split_multiselect(values))
        for original_value in allowed_list:
            feature_name = prefix + safe_name(original_value)
            encoded[feature_name] = 1.0 if normalize_key(original_value) in parsed else 0.0


def init_encoder(schema_path: str | Path | None = None) -> RuntimeEncoder:
    global _ENCODER

    if _ENCODER is not None:
        return _ENCODER

    if schema_path is None:
        from core.config import ENCODING_SCHEMA_PATH
        schema_path = ENCODING_SCHEMA_PATH

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    _ENCODER = RuntimeEncoder(schema=schema)
    return _ENCODER


def get_encoder() -> RuntimeEncoder:
    if _ENCODER is None:
        return init_encoder()
    return _ENCODER