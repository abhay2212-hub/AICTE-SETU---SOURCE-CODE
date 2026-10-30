# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.institutions import (
    ApiKeyCreated,
    ApiKeyRevoked,
    Institution,
    InstitutionDetail,
    WebhookConfig,
    WebhookConfigRequest,
)
from app.services import institutions as service

router = APIRouter(prefix="/institutions", tags=["institutions"])

READERS = require_roles("aicte_admin", "auditor", "institution_admin", "institution_operator")
KEY_ADMINS = require_roles("institution_admin", "aicte_admin")
REAL = source("institutions")


@router.get("", response_model=list[Institution])
def list_institutions(user: User = Depends(READERS), real: bool = Depends(REAL)) -> list[dict]:
    if real:
        with transaction() as conn:
            return service.list_institutions(conn, user)
    return mock("institutions")


@router.get("/{institution_id}", response_model=InstitutionDetail)
def get_institution(
    institution_id: str, user: User = Depends(READERS), real: bool = Depends(REAL)
) -> dict:
    if real:
        with transaction() as conn:
            return service.get_institution(conn, institution_id, user)
    for item in mock("institutions"):
        if item["id"] == institution_id:
            return item
    raise not_found("Institution", institution_id)


@router.post("/{institution_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    institution_id: str, user: User = Depends(KEY_ADMINS), real: bool = Depends(REAL)
) -> dict:
    if real:
        with transaction() as conn:
            return service.create_api_key(conn, institution_id, user)
    key = mock("api_key")
    key["institution_id"] = institution_id
    return key


@router.post("/{institution_id}/api-keys/{key_id}/revoke", response_model=ApiKeyRevoked)
def revoke_api_key(
    institution_id: str,
    key_id: str,
    user: User = Depends(KEY_ADMINS),
    real: bool = Depends(REAL),
) -> dict:
    """Revoke a key; requests sending it get 401 from then on. Revoking twice is a no-op."""
    if real:
        with transaction() as conn:
            return service.revoke_api_key(conn, institution_id, key_id, user)
    key = mock("api_key")
    if key["key_id"] != key_id:
        raise not_found("API key", key_id)
    return {"key_id": key_id, "institution_id": institution_id, "revoked_at": datetime.now(UTC)}


@router.put("/{institution_id}/webhook", response_model=WebhookConfig)
def set_webhook(
    institution_id: str,
    body: WebhookConfigRequest,
    user: User = Depends(KEY_ADMINS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Set the URL that receives batch.committed (signed with X-Signature), or null to
    remove it. Each call with a URL returns a new signing secret, shown once."""
    if real:
        with transaction() as conn:
            return service.set_webhook(conn, institution_id, body.url, user, settings.webhook_key)
    return {
        "institution_id": institution_id,
        "webhook_url": body.url,
        "secret": "whsec_demo_not_a_real_secret" if body.url else None,
    }
