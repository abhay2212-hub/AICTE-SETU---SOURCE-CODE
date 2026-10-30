# Owner: Dev B
"""X-API-Key as an alternative to user auth for system-to-system batch uploads.

A key resolves, through its stored SHA-256 hash, to an institution_operator of its own
institution; audit events record the actor as api_key:<key id>. Unknown and revoked keys are
401. While the batches domain is on fixtures, only the fixture key in mocks/api_key.json works.
"""

from __future__ import annotations

import hmac
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.db import transaction
from app.core.security import get_current_user, require_roles
from app.mocks import mock
from app.models.auth import Role, User


def resolve_api_key(key: str, settings: Settings) -> User:
    if not settings.is_real("batches"):
        fixture = mock("api_key")
        if not hmac.compare_digest(key.encode(), fixture["api_key"].encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        return User(
            id=f"api_key:{fixture['key_id']}",
            role="institution_operator",
            institution_id=fixture["institution_id"],
            display_name="Integration API key",
            demo=True,
        )
    from app.services.institutions import api_key_user

    with transaction() as conn:
        return api_key_user(conn, key)


def api_key_or_roles(*roles: Role) -> Callable[..., User]:
    """Dependency: the X-API-Key user when that header is sent, else the role-checked user."""
    role_guard = require_roles(*roles)

    def guard(
        x_api_key: str | None = Header(
            default=None, description="Institution API key; replaces user auth when sent"
        ),
        authorization: str | None = Header(default=None),
        x_demo_role: str | None = Header(default=None),
        x_demo_institution: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
    ) -> User:
        if x_api_key:
            return resolve_api_key(x_api_key.strip(), settings)
        user = get_current_user(authorization, x_demo_role, x_demo_institution, settings)
        return role_guard(user)

    return guard
