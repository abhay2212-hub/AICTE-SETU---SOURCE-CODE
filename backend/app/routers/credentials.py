# Owner: Dev B
"""Signed student credentials (shared/credentials.md)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header

from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.credentials import (
    Credential,
    CredentialRequest,
    PublicKey,
    Revocation,
    RevocationList,
    RevokeRequest,
    Verification,
    VerifyRequest,
)
from app.services import credentials as service
from app.services import students

router = APIRouter(prefix="/credentials", tags=["credentials"])

STUDENT = require_roles("student")
REAL = source("credentials")
DEMO_STUDENT = Header(
    default=None, description="MOCK_MODE only: act as this student id instead of the demo one"
)


def _fixture_credential(student_id: str, body: CredentialRequest) -> dict:
    """Fixture mode: claims from the fixture student, signed live with the TEST seed."""
    student = mock("students").get(student_id)
    if student is None:
        raise not_found("Student", student_id)
    admission = next(
        (a for a in mock("admissions") if a["student_id"] == student_id),
        {"status": "submitted", "academic_year": "2026-27"},
    )
    claims = service.claim_values(
        {
            "status": admission["status"],
            "institution": student["institution_name"],
            "programme": student["programme_name"],
            "academic_year": admission["academic_year"],
        },
        body.claims,
    )
    payload = service.build_payload(
        student_id=student_id,
        audience=body.audience,
        claims=claims,
        expiry=body.expiry,
        pseudonym_secret=service.TEST_PSEUDONYM_SECRET,
    )
    qr_text = service.sign(payload, service.signing_key(service.TEST_SEED_HEX))
    expires = datetime.fromtimestamp(payload["exp"], UTC)
    return service.credential_out(payload["id"], qr_text, expires, claims)


@router.post("", response_model=Credential, status_code=201)
def issue_credential(
    body: CredentialRequest,
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
    x_demo_student: str | None = DEMO_STUDENT,
) -> dict:
    """Issue an Ed25519-signed credential with the chosen claims for one audience.

    The APAAR ID is never included. Writes an audit event and an access-log entry.
    """
    if real:
        with transaction() as conn:
            student_id = students.resolve_student_id(conn, user, x_demo_student)
            return service.issue(
                conn,
                student_id,
                body.model_dump(),
                settings.credential_signing_key,
                settings.pseudonym_secret,
            )
    return _fixture_credential(students.fixture_student_id(user, x_demo_student), body)


@router.post("/{credential_id}/revoke", response_model=Revocation)
def revoke_credential(
    credential_id: str,
    body: RevokeRequest,
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> dict:
    """Revoke one of the student's own credentials. Repeating it changes nothing."""
    if real:
        with transaction() as conn:
            student_id = students.resolve_student_id(conn, user, x_demo_student)
            return service.revoke(conn, student_id, credential_id, body.reason)
    return {
        "credential_id": credential_id,
        "reason": body.reason,
        "revoked_at": datetime.now(UTC),
    }


@router.get("/revocations", response_model=RevocationList)
def revocations(real: bool = Depends(REAL)) -> dict:
    """Public: offline verifiers sync this list."""
    if real:
        with transaction() as conn:
            return service.revocations(conn)
    return mock("revocations")


@router.get("/public-key", response_model=PublicKey)
def public_key(real: bool = Depends(REAL), settings: Settings = Depends(get_settings)) -> dict:
    """Public: the Ed25519 key verifiers use to check credential signatures."""
    if real:
        key = service.signing_key(settings.credential_signing_key)
        return {
            "algorithm": "Ed25519",
            "key_id": service.key_id(key),
            "public_key_b64": service.public_key_b64(key),
        }
    return mock("public_key")


@router.post("/verify", response_model=Verification, response_model_exclude_none=True)
def verify_credential(
    body: VerifyRequest, real: bool = Depends(REAL), settings: Settings = Depends(get_settings)
) -> dict:
    """Public (verifier or no login): check signature, expiry and revocation.

    Logs the check in the student's access log (audience, purpose, time) and reveals
    nothing beyond the signed claims.
    """
    if real:
        with transaction() as conn:
            return service.verify(conn, body.qr_text, settings.credential_signing_key)
    revoked = {r["credential_id"] for r in mock("revocations")["revoked"]}
    key = service.signing_key(service.TEST_SEED_HEX).verify_key
    result = service.check(body.qr_text, key, revoked)
    result.pop("_payload")
    return result
