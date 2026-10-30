# Owner: Dev A
"""Service orchestrating institution-level anomaly detection and feature importance."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from engine.anomaly.features import (
    FEATURE_NAMES,
    InstitutionFeatureExtractor,
    InstitutionFeatureVector,
)
from engine.anomaly.model import BaseAnomalyModel, IsolationForestModel
from engine.types import AnomalyResult, InstitutionFeatures


class AnomalyDetectionService:
    """Service encapsulating institution anomaly detection workflows.

    Supports model substitution, deterministic training, configurable
    contamination, anomaly scoring, and deviation-based feature importance.
    """

    def __init__(
        self,
        model: BaseAnomalyModel | None = None,
        feature_names: Sequence[str] | None = None,
        contamination: float | str | None = None,
        random_state: int | None = None,
    ) -> None:
        self.feature_names = (
            list(feature_names) if feature_names is not None else list(FEATURE_NAMES)
        )
        self.model = (
            model
            if model is not None
            else IsolationForestModel(
                contamination=contamination,
                random_state=random_state,
            )
        )
        self.extractor = InstitutionFeatureExtractor()
        self._is_fitted: bool = False
        self._means: dict[str, float] = {}
        self._stds: dict[str, float] = {}

    def fit(
        self,
        items: Sequence[InstitutionFeatures | InstitutionFeatureVector | dict[str, Any]],
    ) -> AnomalyDetectionService:
        """Fit the anomaly detection model and compute baseline dataset statistics."""
        if not items:
            raise ValueError("Cannot fit anomaly model on empty dataset.")

        vectors = [self._to_vector(item) for item in items]
        X = np.array([v.to_array(self.feature_names) for v in vectors], dtype=np.float64)

        # Compute dataset mean and std per feature for feature importance explanations
        means = np.mean(X, axis=0)
        stds = np.std(X, axis=0)

        for i, name in enumerate(self.feature_names):
            self._means[name] = float(means[i])
            self._stds[name] = float(stds[i])

        self.model.fit(X, self.feature_names)
        self._is_fitted = True
        return self

    def predict(
        self,
        items: Sequence[InstitutionFeatures | InstitutionFeatureVector | dict[str, Any]],
    ) -> list[AnomalyResult]:
        """Predict anomaly status, anomaly score, and influential features for each item."""
        if not items:
            return []

        vectors = [self._to_vector(item) for item in items]

        if not self._is_fitted:
            self.fit(vectors)

        X = np.array([v.to_array(self.feature_names) for v in vectors], dtype=np.float64)
        raw_preds = self.model.predict(X)
        scores = self.model.score_samples(X)

        results: list[AnomalyResult] = []
        for i, vec in enumerate(vectors):
            pred_label = "anomalous" if raw_preds[i] == -1 else "normal"
            score_val = float(scores[i])
            feat_dict = vec.to_dict()
            top_features = self._explain(feat_dict, top_k=3)

            results.append(
                AnomalyResult(
                    institution_id=vec.institution_id,
                    score=score_val,
                    prediction=pred_label,
                    top_features=top_features,
                    feature_vector=feat_dict,
                )
            )

        return results

    def fit_predict(
        self,
        items: Sequence[InstitutionFeatures | InstitutionFeatureVector | dict[str, Any]],
    ) -> list[AnomalyResult]:
        """Convenience method to fit and predict on a batch of institutions."""
        self.fit(items)
        return self.predict(items)

    def _explain(self, feature_dict: dict[str, float], top_k: int = 3) -> list[str]:
        """Explain influential features using deviation from the dataset mean."""
        deviations: list[tuple[str, float]] = []

        for name in self.feature_names:
            val = feature_dict.get(name, 0.0)
            mean = self._means.get(name, 0.0)
            std = self._stds.get(name, 1.0)
            denom = std if std > 1e-4 else 1.0
            # Normalized z-score deviation
            z = (val - mean) / denom
            deviations.append((name, z))

        # Sort primarily by positive deviation (risk factors higher than normal)
        # then absolute deviation
        deviations.sort(key=lambda item: (item[1], abs(item[1])), reverse=True)

        # Select features that deviate positively, or top deviators
        top = [name for name, z in deviations[:top_k] if abs(z) > 1e-4]
        if not top and deviations:
            top = [deviations[0][0]]
        return top

    def _to_vector(
        self,
        item: InstitutionFeatures | InstitutionFeatureVector | dict[str, Any],
    ) -> InstitutionFeatureVector:
        if isinstance(item, InstitutionFeatureVector):
            return item
        if isinstance(item, InstitutionFeatures):
            return self.extractor.extract(item.institution_id, item)
        if isinstance(item, dict):
            inst_id = str(item.get("institution_id") or "unknown_inst")
            return self.extractor.extract(inst_id, item)
        raise TypeError(f"Unsupported item type for feature extraction: {type(item)}")
