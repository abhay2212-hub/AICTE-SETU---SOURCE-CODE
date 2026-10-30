# Owner: Dev A
"""Engine configuration defaults reading from environment variables."""

from __future__ import annotations

import os

MATCH_THRESHOLD: float = float(os.getenv("MATCH_THRESHOLD", "0.85"))
MODEL_VERSION: str = os.getenv("MODEL_VERSION", "0.1.0")
SHARED_CONTACT_THRESHOLD: int = int(os.getenv("SHARED_CONTACT_THRESHOLD", "5"))
BLOOM_BITS: int = int(os.getenv("BLOOM_BITS", "1024"))

# Anomaly detection configuration
ANOMALY_CONTAMINATION: float = float(os.getenv("ANOMALY_CONTAMINATION", "0.1"))
MODEL_RANDOM_SEED: int = int(os.getenv("MODEL_RANDOM_SEED", "42"))

# Integrity scoring weights (must sum or scale according to scoring policy)
SIGNAL_WEIGHT: float = float(os.getenv("SIGNAL_WEIGHT", "0.40"))
ANOMALY_WEIGHT: float = float(os.getenv("ANOMALY_WEIGHT", "0.35"))
BLIND_MATCH_WEIGHT: float = float(os.getenv("BLIND_MATCH_WEIGHT", "0.25"))

# Signal severity deduction points
SEVERITY_WEIGHT_ERROR: float = float(os.getenv("SEVERITY_WEIGHT_ERROR", "25.0"))
SEVERITY_WEIGHT_REVIEW: float = float(os.getenv("SEVERITY_WEIGHT_REVIEW", "15.0"))
SEVERITY_WEIGHT_WARNING: float = float(os.getenv("SEVERITY_WEIGHT_WARNING", "8.0"))
SEVERITY_WEIGHT_INFO: float = float(os.getenv("SEVERITY_WEIGHT_INFO", "2.0"))

# Score thresholds for risk classification (100 = cleanest, 0 = worst)
SCORE_THRESHOLD_LOW: float = float(os.getenv("SCORE_THRESHOLD_LOW", "80.0"))
SCORE_THRESHOLD_MEDIUM: float = float(os.getenv("SCORE_THRESHOLD_MEDIUM", "60.0"))
SCORE_THRESHOLD_HIGH: float = float(os.getenv("SCORE_THRESHOLD_HIGH", "40.0"))
