from typing import Any
import joblib
import json
import math
from pathlib import Path


_POLICY = None


class HybridPolicy:
    def __init__(self, config: dict, classifier_bundle: dict, actions_metadata: dict):
        self.config = config
        self.classifier_bundle = classifier_bundle
        self.actions_metadata = actions_metadata

        self.classifier_model = classifier_bundle["model"]
        self.classifier_version = str(classifier_bundle.get("version", "unknown"))

        self.actions: list[str] = list(actions_metadata.get("actions", []))
        self.action_descriptions: dict[str, str] = actions_metadata.get(
            "action_descriptions", {}
        )

        self.classifier_weight = float(config.get("classifier_weight", 0.6))
        self.bandit_weight = float(config.get("bandit_weight", 0.4))
        self.min_rewarded_events_for_personalization = int(
            config.get("min_rewarded_events_for_personalization", 3)
        )
        self.hybrid_policy_version = str(config.get("hybrid_policy_version", "unknown"))
        self.guardrail_policy_version = str(
            config.get("guardrail_policy_version", "unknown")
        )

    def decide(
        self,
        encoded_features: dict[str, float],
        feature_vector: list[float],
        bandit_runtime: Any,
        rewarded_events_count: int,
    ) -> dict[str, Any]:
        allowed_actions = self._shortlist_actions(encoded_features)
        classifier_scores = self._classifier_action_scores(feature_vector)

        clf_scores_allowed = {
            action: float(classifier_scores.get(action, 0.0))
            for action in allowed_actions
        }

        classifier_family = self._argmax(clf_scores_allowed)
        classifier_confidence = float(clf_scores_allowed.get(classifier_family, 0.0))

        if rewarded_events_count < self.min_rewarded_events_for_personalization:
            selected_action = classifier_family
            confidence = classifier_confidence

            return {
                "recommendation_family": selected_action,
                "selected_action": selected_action,
                "classifier_family": classifier_family,
                "classifier_confidence": classifier_confidence,
                "bandit_action": None,
                "policy_mode": "cold_start_classifier_first",
                "policy_version": self.hybrid_policy_version,
                "confidence": confidence,
                "decision_meta": {
                    "allowed_actions": allowed_actions,
                    "classifier_scores": clf_scores_allowed,
                    "bandit_scores": {a: 0.0 for a in allowed_actions},
                    "hybrid_scores": clf_scores_allowed,
                    "guardrail_policy_version": self.guardrail_policy_version,
                    "hybrid_policy_version": self.hybrid_policy_version,
                    "classifier_version": self.classifier_version,
                    "personalization_used": False,
                    "rewarded_events_count": rewarded_events_count,
                    "explanation": self._build_explanation(
                        selected_action=selected_action,
                        policy_mode="cold_start_classifier_first",
                    ),
                },
            }

        bandit_action, bandit_scores = bandit_runtime.choose(
            feature_vector=feature_vector,
            allowed_actions=allowed_actions,
        )

        hybrid_scores = {
            action: (
                self.classifier_weight * clf_scores_allowed.get(action, 0.0)
            ) + (
                self.bandit_weight * float(bandit_scores.get(action, 0.0))
            )
            for action in allowed_actions
        }

        selected_action = self._argmax(hybrid_scores)
        confidence = float(hybrid_scores.get(selected_action, 0.0))

        return {
            "recommendation_family": selected_action,
            "selected_action": selected_action,
            "classifier_family": classifier_family,
            "classifier_confidence": classifier_confidence,
            "bandit_action": bandit_action,
            "policy_mode": "hybrid_option_c_bandit_active",
            "policy_version": self.hybrid_policy_version,
            "confidence": confidence,
            "decision_meta": {
                "allowed_actions": allowed_actions,
                "classifier_scores": clf_scores_allowed,
                "bandit_scores": {
                    a: float(bandit_scores.get(a, 0.0)) for a in allowed_actions
                },
                "hybrid_scores": hybrid_scores,
                "guardrail_policy_version": self.guardrail_policy_version,
                "hybrid_policy_version": self.hybrid_policy_version,
                "classifier_version": self.classifier_version,
                "personalization_used": True,
                "rewarded_events_count": rewarded_events_count,
                "explanation": self._build_explanation(
                    selected_action=selected_action,
                    policy_mode="hybrid_option_c_bandit_active",
                ),
            },
        }

    def _classifier_action_scores(self, feature_vector: list[float]) -> dict[str, float]:
        probs = self.classifier_model.predict_proba([feature_vector])[0]
        classes = list(getattr(self.classifier_model, "classes_", self.actions))

        raw_scores = {
            str(label): float(prob)
            for label, prob in zip(classes, probs)
        }

        return {
            action: float(raw_scores.get(action, 0.0))
            for action in self.actions
        }

    def _shortlist_actions(self, encoded_features: dict[str, float]) -> list[str]:
        risk_code = float(encoded_features.get("risk_level_code", 0.0))
        exposure = float(encoded_features.get("exposure_code", 0.0))
        readiness = float(encoded_features.get("readiness_code", 2.0))
        efficacy = float(encoded_features.get("coping_efficacy_code", 2.0))

        risky_location = int(
            encoded_features.get("location_parties_events", 0.0)
            or encoded_features.get("location_friend_s_place", 0.0)
            or encoded_features.get("location_friends_place", 0.0)
        )

        allowed: set[str] = set()

        # Higher risk -> safer / stabilizing families
        if risk_code >= 2.0:
            allowed.update(
                [
                    "Support_Routing_or_Safe_Space",
                    "Grounding_and_Coping",
                    "Coping_Skill_Training",
                ]
            )
        else:
            allowed.update(
                [
                    "Grounding_and_Coping",
                    "Routine_and_Progress",
                    "Motivational_Message",
                ]
            )

        if "Coping_Prompt" in self.actions:
            if efficacy <= 1.0 or (efficacy <= 2.0 and readiness <= 2.0):
                allowed.add("Coping_Prompt")

        if exposure >= 2.0 or risky_location == 1:
            if "Support_Routing_or_Safe_Space" in self.actions:
                allowed.add("Support_Routing_or_Safe_Space")
            if "Grounding_and_Coping" in self.actions:
                allowed.add("Grounding_and_Coping")

        if readiness <= 1.0:
            if "Motivational_Message" in self.actions:
                allowed.add("Motivational_Message")
            if "Coping_Skill_Training" in self.actions:
                allowed.add("Coping_Skill_Training")
            if "Grounding_and_Coping" in self.actions:
                allowed.add("Grounding_and_Coping")

        if efficacy <= 1.0:
            if "Grounding_and_Coping" in self.actions:
                allowed.add("Grounding_and_Coping")
            if "Coping_Skill_Training" in self.actions:
                allowed.add("Coping_Skill_Training")
            if "Coping_Prompt" in self.actions:
                allowed.add("Coping_Prompt")

        if readiness >= 2.0 and efficacy >= 2.0:
            if "Routine_and_Progress" in self.actions:
                allowed.add("Routine_and_Progress")

        final_allowed = [a for a in sorted(allowed) if a in self.actions]
        return final_allowed if final_allowed else list(self.actions)

    @staticmethod
    def _argmax(score_map: dict[str, float]) -> str:
        if not score_map:
            raise ValueError("Empty score map.")
        return max(sorted(score_map), key=lambda action: score_map[action])

    @staticmethod
    def _build_explanation(selected_action: str, policy_mode: str) -> str:
        if policy_mode == "cold_start_classifier_first":
            return f"Selected {selected_action} using classifier-first cold-start policy."
        return f"Selected {selected_action} using hybrid classifier + bandit policy."


def init_policy(
    policy_config_path: str | Path | None = None,
    classifier_path: str | Path | None = None,
    actions_metadata_path: str | Path | None = None,
) -> HybridPolicy:
    global _POLICY

    if _POLICY is not None:
        return _POLICY

    from core.config import (
        POLICY_CONFIG_PATH,
        CLASSIFIER_JOBLIB_PATH,
        ACTIONS_METADATA_PATH,
    )

    if policy_config_path is None:
        policy_config_path = POLICY_CONFIG_PATH
    if actions_metadata_path is None:
        actions_metadata_path = ACTIONS_METADATA_PATH
    if classifier_path is None:
        classifier_path = CLASSIFIER_JOBLIB_PATH

    with open(policy_config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    with open(actions_metadata_path, "r", encoding="utf-8") as f:
        actions_metadata = json.load(f)

    classifier_bundle = joblib.load(classifier_path)

    _POLICY = HybridPolicy(
        config=config,
        classifier_bundle=classifier_bundle,
        actions_metadata=actions_metadata,
    )
    return _POLICY


def get_policy() -> HybridPolicy:
    if _POLICY is None:
        return init_policy()
    return _POLICY