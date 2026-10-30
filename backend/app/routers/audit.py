# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.audit import verify_chain
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock
from app.models.audit import AuditVerifyResult
from app.services import audit_store, realtime

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "/verify",
    response_model=AuditVerifyResult,
    dependencies=[Depends(require_roles("aicte_admin", "auditor"))],
)
def verify_audit_chain(background: BackgroundTasks, real: bool = Depends(source("audit"))) -> dict:
    """Recompute the hash chain; on a break, broadcast audit.tamper_detected."""
    if real:
        with transaction() as conn:
            result = audit_store.verify(conn)
        if not result["ok"]:
            payload = {**result, "detected_at": datetime.now(UTC).isoformat()}
            payload.pop("ok")
            background.add_task(realtime.publish, [("audit.tamper_detected", payload)])
        return result
    events = mock("audit_events")
    broken = verify_chain(events)
    return {"ok": broken is None, "first_broken_index": broken, "checked": len(events)}
