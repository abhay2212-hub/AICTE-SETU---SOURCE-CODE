# Owner: Dev B
"""Authentication and role guards.

Mock mode: the user comes from the X-Demo-Role and X-Demo-Institution headers.
Otherwise: a Supabase access token in the Authorization header, verified against the
project JWKS (ES256/RS256) or, for legacy projects, SUPABASE_JWT_SECRET (HS256).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import get_args

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.models.auth import Role, User

ROLES: tuple[str, ...] = get_args(Role)
DEFAULT_DEMO_ROLE: Role = "aicte_admin"
DEMO_USER_IDS: dict[str, str] = {
    # The demo student maps to the first student in the mock fixtures.
    "student": "40000000-0000-4000-8000-000000000001",
}


def demo_user(role: str | None, institution: str | None) -> User:
    role = (role or DEFAULT_DEMO_ROLE).strip()
    if role not in ROLES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown X-Demo-Role '{role}'. Use one of: {ROLES}"
        )
    return User(
        id=DEMO_USER_IDS.get(role, f"demo-{role}"),
        role=role,
        institution_id=institution or None,
        display_name=f"Demo {role.replace('_', ' ')}",
        demo=True,
    )


_ASYMMETRIC = ["ES256", "RS256"]


@lru_cache(maxsize=4)
def jwks_client(supabase_url: str) -> jwt.PyJWKClient:
    """Cached JWKS client for the project; keys are cached and refreshed on unknown kid."""
    url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600, timeout=5)


def decode_token(token: str, settings: Settings) -> dict:
    """Verify a Supabase access token.

    Asymmetric tokens (ES256, RS256) are checked against the project JWKS. HS256 tokens are
    accepted only when SUPABASE_JWT_SECRET is set (legacy projects). Audience must be
    "authenticated"; the issuer must be {SUPABASE_URL}/auth/v1 whenever SUPABASE_URL is set.
    """
    algorithm = jwt.get_unverified_header(token).get("alg")
    issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1" if settings.supabase_url else None
    options = {"require": ["exp", "sub"]} if issuer else {"require": ["sub"]}
    if algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise jwt.InvalidTokenError("HS256 tokens need SUPABASE_JWT_SECRET")
        key: object = settings.supabase_jwt_secret
        algorithms = ["HS256"]
    elif algorithm in _ASYMMETRIC:
        if not settings.supabase_url:
            raise jwt.InvalidTokenError("SUPABASE_URL is needed to fetch the JWKS")
        key = jwks_client(settings.supabase_url).get_signing_key_from_jwt(token).key
        algorithms = _ASYMMETRIC
    else:
        raise jwt.InvalidTokenError(f"Unsupported algorithm {algorithm}")
    return jwt.decode(
        token,
        key,
        algorithms=algorithms,
        audience="authenticated",
        issuer=issuer,
        options=options,
    )


def _user_from_jwt(authorization: str | None, settings: Settings) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1], settings)
    except (jwt.PyJWTError, jwt.PyJWKClientError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc
    app_meta = claims.get("app_metadata") or {}
    role = app_meta.get("role")
    if role not in ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Token has no platform role")
    return User(
        id=claims["sub"],
        role=role,
        institution_id=app_meta.get("institution_id"),
        display_name=claims.get("email"),
        demo=False,
        student_id=app_meta.get("student_id"),
    )


def get_current_user(
    authorization: str | None = Header(default=None),
    x_demo_role: str | None = Header(default=None),
    x_demo_institution: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> User:
    if settings.mock_mode:
        return demo_user(x_demo_role, x_demo_institution)
    return _user_from_jwt(authorization, settings)


INSTITUTION_ROLES = ("institution_admin", "institution_operator")


def scoped_institution(user: User, requested: str | None = None) -> str | None:
    """Institution a query or write is limited to.

    Institution users are always pinned to their own institution, taken from the
    authenticated user and never from the request; asking for another one is 403.
    Everyone else gets ``requested`` (None means all institutions).
    """
    if user.role not in INSTITUTION_ROLES:
        return requested
    if not user.institution_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User is not linked to an institution")
    if requested and requested != user.institution_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your institution")
    return user.institution_id


def require_roles(*roles: Role) -> Callable[..., User]:
    """Dependency that returns the current user, or 403 if their role is not in ``roles``."""

    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Role '{user.role}' may not access this resource"
            )
        return user

    return guard
