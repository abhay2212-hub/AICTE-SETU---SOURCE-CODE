# Owner: Dev A
"""Engine endpoints for metadata, health, and blind match."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.security import require_roles
from app.models.engine import (
    AnomalyPrediction,
    AnomalyRequest,
    BlindMatchRequest,
    BlindMatchStudentInput,
    EngineHealth,
    EngineInfo,
    IntegrityScore,
    IntegrityScoreRequest,
    MatchCase,
    Signal,
    SignalsRequest,
)

router = APIRouter(
    prefix="/engine",
    tags=["engine"],
    dependencies=[Depends(require_roles("aicte_admin"))],
)


@router.get("", response_model=EngineInfo)
def get_engine(settings: Settings = Depends(get_settings)) -> EngineInfo:
    """Return engine metadata and configuration."""
    return EngineInfo(
        name="Integrity Intelligence Engine",
        version=settings.model_version,
        status="active",
        match_threshold=settings.match_threshold,
        model_version=settings.model_version,
    )


@router.get("/health", response_model=EngineHealth)
def get_engine_health(settings: Settings = Depends(get_settings)) -> EngineHealth:
    """Return engine health and import status."""
    try:
        import engine

        engine_ok = True
        version = getattr(engine, "__version__", settings.model_version)
    except ImportError:
        engine_ok = False
        version = settings.model_version

    return EngineHealth(
        status="ok",
        version=version,
        engine_ok=engine_ok,
    )


@router.post("/blind-match", response_model=list[MatchCase])
def post_blind_match(
    body: BlindMatchRequest | list[BlindMatchStudentInput],
    settings: Settings = Depends(get_settings),
) -> list[MatchCase]:
    """Execute in-memory privacy-preserving blind match and exact APAAR duplicate detection."""
    from engine.blind_match import BlindMatchService, StudentRecord
    from fastapi import HTTPException

    secret = settings.blind_match_secret
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="BLIND_MATCH_SECRET is not configured on the platform.",
        )

    raw_records = body.records if isinstance(body, BlindMatchRequest) else body
    threshold = (
        body.threshold
        if isinstance(body, BlindMatchRequest) and body.threshold is not None
        else settings.match_threshold
    )

    students = [
        StudentRecord(
            student_id=r.student_id,
            institution_id=r.institution_id,
            student_name=r.student_name,
            dob=r.dob,
            father_name=r.father_name,
            mother_name=r.mother_name,
            apaar_id=r.apaar_id,
        )
        for r in raw_records
    ]

    service = BlindMatchService(
        secret=secret,
        threshold=threshold,
    )
    matches = service.run_blind_match(students, threshold=threshold)

    return [
        MatchCase(
            case_id=m.case_id,
            institution_a=m.institution_a,
            institution_b=m.institution_b,
            student_a_id=m.student_a_id,
            student_b_id=m.student_b_id,
            similarity_score=m.similarity_score,
            confidence=m.confidence,
            matched_fields=m.matched_fields,
            status=m.status,
            created_at=m.created_at,
        )
        for m in matches
    ]


@router.post("/signals", response_model=list[Signal])
def post_signals(
    body: SignalsRequest | dict[str, Any] | list[dict[str, Any]],
) -> list[Signal]:
    """Execute rule-based integrity signals against institution data."""
    from engine.signals import execute_signals

    if isinstance(body, SignalsRequest):
        payload: dict[str, Any] = body.model_dump()
    elif isinstance(body, (dict, list)):
        payload = body
    else:
        payload = {}

    signals = execute_signals(payload)

    return [
        Signal(
            signal_id=s.signal_id,
            institution_id=s.institution_id,
            signal_name=s.signal_name,
            severity=s.severity,
            score=s.score,
            evidence=s.evidence,
            description=s.description,
            created_at=s.created_at,
        )
        for s in signals
    ]


@router.post(
    "/anomaly",
    response_model=list[AnomalyPrediction] | AnomalyPrediction,
)
def post_anomaly(
    body: AnomalyRequest | dict[str, Any] | list[dict[str, Any]],
) -> list[AnomalyPrediction] | AnomalyPrediction:
    """Execute in-memory ML anomaly detection across institutions."""
    from engine.anomaly.service import AnomalyDetectionService
    from fastapi import HTTPException

    is_single = False
    if isinstance(body, AnomalyRequest):
        payload: dict[str, Any] = body.model_dump()
        items = payload.get("institutions") or payload.get("features") or []
    elif isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        if "institutions" in body and isinstance(body["institutions"], list):
            items = body["institutions"]
        elif "features" in body and isinstance(body["features"], list):
            items = body["features"]
        elif not body:
            return []
        else:
            items = [body]
            is_single = True
    else:
        raise HTTPException(status_code=400, detail="Invalid request payload")

    if not items:
        return []

    service = AnomalyDetectionService()
    try:
        results = service.fit_predict(items)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Anomaly detection failed: {exc}") from exc

    predictions = [
        AnomalyPrediction(
            institution_id=r.institution_id,
            score=r.score,
            prediction=r.prediction,
            top_features=r.top_features,
            feature_vector=r.feature_vector,
        )
        for r in results
    ]

    return predictions[0] if is_single and predictions else predictions


@router.post(
    "/integrity-score",
    response_model=IntegrityScore | list[IntegrityScore],
)
def post_integrity_score(
    body: IntegrityScoreRequest | dict[str, Any] | list[dict[str, Any]],
) -> IntegrityScore | list[IntegrityScore]:
    """Calculate in-memory Institution Integrity Score."""
    from engine.scoring.service import IntegrityScoringService
    from fastapi import HTTPException

    if isinstance(body, IntegrityScoreRequest):
        payload: dict[str, Any] = body.model_dump()
    elif isinstance(body, (dict, list)):
        payload = body
    else:
        raise HTTPException(status_code=400, detail="Invalid request payload")

    if isinstance(payload, list):
        service = IntegrityScoringService()
        scores = service.calculate_batch(payload)
        return [
            IntegrityScore(
                institution_id=s.institution_id,
                score=s.score,
                risk_level=s.risk_level,  # type: ignore[arg-type]
                components=s.components,
                generated_at=s.generated_at,
                signals=[
                    Signal(
                        signal_id=sig.signal_id,
                        institution_id=sig.institution_id,
                        signal_name=sig.signal_name,
                        severity=sig.severity,
                        score=sig.score,
                        evidence=sig.evidence,
                        description=sig.description,
                        created_at=sig.created_at,
                    )
                    for sig in s.signals
                ],
            )
            for s in scores
        ]

    if not payload:
        raise HTTPException(status_code=400, detail="Payload cannot be empty")

    service = IntegrityScoringService()
    try:
        score_res = service.calculate_from_data(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Scoring calculation failed: {exc}") from exc

    return IntegrityScore(
        institution_id=score_res.institution_id,
        score=score_res.score,
        risk_level=score_res.risk_level,  # type: ignore[arg-type]
        components=score_res.components,
        generated_at=score_res.generated_at,
        signals=[
            Signal(
                signal_id=sig.signal_id,
                institution_id=sig.institution_id,
                signal_name=sig.signal_name,
                severity=sig.severity,
                score=sig.score,
                evidence=sig.evidence,
                description=sig.description,
                created_at=sig.created_at,
            )
            for sig in score_res.signals
        ],
    )


@router.post("/evaluate", response_model=dict[str, Any])
def post_evaluate(
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute complete in-memory evaluation harness and benchmarking."""
    from engine.evaluation.datasets import EvaluationDataset
    from engine.evaluation.service import EvaluationService
    from fastapi import HTTPException

    if body is not None and not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request payload must be a JSON object.")

    try:
        if not body:
            dataset = EvaluationDataset.create_synthetic_benchmark_dataset()
        else:
            dataset = EvaluationDataset.from_dict(body)

        service = EvaluationService()
        report = service.run_full_evaluation(dataset)
        return report.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Evaluation failed: {exc}") from exc
