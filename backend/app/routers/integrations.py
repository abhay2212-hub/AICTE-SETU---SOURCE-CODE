# Owner: Dev B
"""SIMULATED government-system integrations (AICTE portal SSO, APAAR registry)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import demo_user, require_roles
from app.mocks import require_mock
from app.models.integrations import (
    ApaarVerifyRequest,
    ApaarVerifyResponse,
    SsoMockRequest,
    SsoMockResponse,
)
from app.services.validation import mask_apaar, validate_apaar

router = APIRouter(prefix="/integrations", tags=["integrations"])

# SIMULATED registry: synthetic APAAR IDs start with 9999.
_SIMULATED_PREFIX = "9999"


@router.post("/sso/mock", response_model=SsoMockResponse)
def sso_mock(body: SsoMockRequest) -> SsoMockResponse:
    """SIMULATED AICTE portal SSO: returns a demo user and the headers to send in mock mode."""
    require_mock()
    user = demo_user(body.role, body.institution_id)
    headers = {"X-Demo-Role": user.role}
    if user.institution_id:
        headers["X-Demo-Institution"] = user.institution_id
    return SsoMockResponse(user=user, demo_headers=headers)


@router.post(
    "/apaar/verify",
    response_model=ApaarVerifyResponse,
    dependencies=[
        Depends(require_roles("institution_admin", "institution_operator", "aicte_admin"))
    ],
)
def apaar_verify(body: ApaarVerifyRequest) -> ApaarVerifyResponse:
    """SIMULATED APAAR registry lookup. Format check is real; existence is simulated."""
    require_mock()
    code = validate_apaar(body.apaar_id, body.opted_out)
    masked = mask_apaar((body.apaar_id or "").strip() or None)
    if code is None:
        found = body.apaar_id.strip().startswith(_SIMULATED_PREFIX)
        result = "found" if found else "not_found"
    else:
        result = {"APAAR_OPTED_OUT": "opted_out", "APAAR_MISSING": "missing"}.get(
            code, "invalid_format"
        )
    return ApaarVerifyResponse(
        apaar_id_masked=masked, result=result, rule_code=code.value if code else None
    )
