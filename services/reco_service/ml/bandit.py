import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


_BANDIT = None


@dataclass
class LinUCBPolicy:
    actions: list[str]
    alpha: float
    d: int
    A: dict[str, np.ndarray]
    b: dict[str, np.ndarray]
    bundle_path: Path | None = None
    bundle: dict[str, Any] | None = None

    @classmethod
    def from_bundle(cls, bundle: dict, actions: list[str], d: int, bundle_path: Path | None = None) -> "LinUCBPolicy":
        state = bundle.get("bandit_state", {}) or {}
        alpha = float(state.get("alpha", state.get("exploration_alpha", 1.0)))

        a_state = state.get("A", {}) or {}
        b_state = state.get("b", {}) or {}

        A: dict[str, np.ndarray] = {}
        b: dict[str, np.ndarray] = {}

        for action in actions:
            if action in a_state:
                A[action] = np.array(a_state[action], dtype=float)
            else:
                A[action] = np.eye(d, dtype=float)

            if action in b_state:
                b[action] = np.array(b_state[action], dtype=float)
            else:
                b[action] = np.zeros(d, dtype=float)

        return cls(
            actions=actions,
            alpha=alpha,
            d=d,
            A=A,
            b=b,
            bundle_path=bundle_path,
            bundle=bundle,
        )

    def score_action(self, action: str, feature_vector: list[float] | np.ndarray) -> float:
        x = np.asarray(feature_vector, dtype=float)
        A_inv = np.linalg.inv(self.A[action])
        theta = A_inv @ self.b[action]
        mean = float(theta @ x)
        bonus = float(self.alpha * np.sqrt(x @ A_inv @ x))
        return mean + bonus

    def choose(
        self,
        feature_vector: list[float] | np.ndarray,
        allowed_actions: list[str],
    ) -> tuple[str, dict[str, float]]:
        scores = {
            action: self.score_action(action, feature_vector)
            for action in allowed_actions
        }
        chosen = max(sorted(allowed_actions), key=lambda a: scores[a])
        return chosen, scores

    def update_from_feedback(
        self,
        action: str,
        encoded_features: dict[str, float] | None = None,
        feature_vector: list[float] | np.ndarray | None = None,
        reward: float = 0.0,
    ) -> None:
        if feature_vector is None:
            if encoded_features is None:
                raise ValueError("Either feature_vector or encoded_features must be provided.")
            feature_vector = self._vector_from_encoded(encoded_features)

        x = np.asarray(feature_vector, dtype=float)

        if action not in self.A:
            self.A[action] = np.eye(self.d, dtype=float)
        if action not in self.b:
            self.b[action] = np.zeros(self.d, dtype=float)

        self.A[action] = self.A[action] + np.outer(x, x)
        self.b[action] = self.b[action] + float(reward) * x

    def _vector_from_encoded(self, encoded_features: dict[str, float]) -> np.ndarray:
        from ml.encoder import get_encoder

        encoder = get_encoder()
        ordered = encoder.vector(encoded_features)
        return np.asarray(ordered, dtype=float)

    def get_state(self) -> dict:
        return {
            "alpha": self.alpha,
            "A": {k: v.tolist() for k, v in self.A.items()},
            "b": {k: v.tolist() for k, v in self.b.items()},
        }

    def save(self, out_path: Path | None = None) -> None:
        target_path = out_path or self.bundle_path
        if target_path is None:
            raise ValueError("No bandit output path configured.")

        bundle = dict(self.bundle or {})
        bundle["bandit_state"] = self.get_state()

        with Path(target_path).open("wb") as f:
            pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)


def init_bandit_runtime(bundle_path: str | Path | None = None) -> LinUCBPolicy:
    global _BANDIT

    if _BANDIT is not None:
        return _BANDIT

    from core.config import BANDIT_RUNTIME_PATH, ACTIONS_METADATA_PATH
    import json

    if bundle_path is None:
        bundle_path = BANDIT_RUNTIME_PATH

    bundle_path = Path(bundle_path)

    with open(ACTIONS_METADATA_PATH, "r", encoding="utf-8") as f:
        actions_meta = json.load(f)

    actions = list(actions_meta.get("actions", []))
    if not actions:
        raise ValueError("No actions found in actions metadata.")

    with bundle_path.open("rb") as f:
        bundle = pickle.load(f)

    from ml.encoder import get_encoder
    encoder = get_encoder()
    d = len(encoder.feature_cols)

    _BANDIT = LinUCBPolicy.from_bundle(
        bundle=bundle,
        actions=actions,
        d=d,
        bundle_path=bundle_path,
    )
    return _BANDIT


def get_bandit_runtime() -> LinUCBPolicy:
    if _BANDIT is None:
        return init_bandit_runtime()
    return _BANDIT