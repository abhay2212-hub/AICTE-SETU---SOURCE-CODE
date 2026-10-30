# Owner: Dev A
"""Modular anomaly detection models for institution risk assessment."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from engine.config import ANOMALY_CONTAMINATION, MODEL_RANDOM_SEED


class BaseAnomalyModel(ABC):
    """Abstract base class for institution anomaly detection models.

    Allows plugging in alternate algorithms (e.g. LOF, One-Class SVM,
    or deep autoencoders) without changing caller code.
    """

    @abstractmethod
    def fit(
        self,
        X: np.ndarray,
        feature_names: Sequence[str] | None = None,
    ) -> BaseAnomalyModel:
        """Fit the model on feature matrix X (shape: [n_samples, n_features])."""

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict labels for samples in X: 1 for normal, -1 for anomalous."""

    @abstractmethod
    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Return anomaly scores in [0.0, 1.0], where higher indicates more anomalous."""


class IsolationForestModel(BaseAnomalyModel):
    """Isolation Forest anomaly detection model using scikit-learn.

    Features deterministic random state, configurable contamination,
    and normalized [0.0, 1.0] anomaly scoring.
    """

    def __init__(
        self,
        contamination: float | str | None = None,
        random_state: int | None = None,
        n_estimators: int = 100,
        **kwargs: Any,
    ) -> None:
        raw_contamination = contamination if contamination is not None else ANOMALY_CONTAMINATION
        if isinstance(raw_contamination, str) and raw_contamination.lower() != "auto":
            try:
                self.contamination: float | str = float(raw_contamination)
            except ValueError:
                self.contamination = "auto"
        else:
            self.contamination = raw_contamination

        self.random_state = random_state if random_state is not None else MODEL_RANDOM_SEED
        self.n_estimators = n_estimators
        self.feature_names: list[str] = []
        self._is_fitted: bool = False

        self.model = IsolationForest(
            n_estimators=self.n_estimators,
            contamination=self.contamination,
            random_state=self.random_state,
            **kwargs,
        )

    def fit(
        self,
        X: np.ndarray,
        feature_names: Sequence[str] | None = None,
    ) -> IsolationForestModel:
        """Fit Isolation Forest on feature matrix X."""
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)

        if feature_names is not None:
            self.feature_names = list(feature_names)
        else:
            self.feature_names = [f"f_{i}" for i in range(X_arr.shape[1])]

        self.model.fit(X_arr)
        self._is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Return 1 for normal, -1 for anomalous."""
        if not self._is_fitted:
            raise RuntimeError("IsolationForestModel must be fitted before predict.")
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        return self.model.predict(X_arr)

    def score_samples(self, X: np.ndarray) -> np.ndarray:
        """Compute anomaly score in [0.0, 1.0], where higher indicates more anomalous.

        In scikit-learn, IsolationForest.score_samples returns the opposite of
        the anomaly score defined in the original Liu et al. paper:
        score_samples = -s(x) where s(x) is in (0, 1).
        Thus, -score_samples directly yields the normalized anomaly score.
        """
        if not self._is_fitted:
            raise RuntimeError("IsolationForestModel must be fitted before score_samples.")
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)

        # Scikit-learn score_samples is negative; negate to get s(x) in (0, 1)
        raw_scores = -self.model.score_samples(X_arr)
        # Clamp strictly to [0.0, 1.0]
        clamped = np.clip(raw_scores, 0.0, 1.0)
        return np.round(clamped, 4)

    def decision_function(self, X: np.ndarray) -> np.ndarray:
        """Return the raw decision function values."""
        if not self._is_fitted:
            raise RuntimeError("IsolationForestModel must be fitted before decision_function.")
        X_arr = np.asarray(X, dtype=np.float64)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(1, -1)
        return self.model.decision_function(X_arr)
