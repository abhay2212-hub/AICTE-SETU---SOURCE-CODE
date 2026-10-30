# Owner: Dev B
"""Institutions, programmes and integration API keys on Postgres."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

import psycopg
from fastapi import HTTPException, status

from app.core.security import scoped_institution
from app.models.auth import User
from app.services import audit_store, outbound_webhooks
from app.services.batches import as_uuid


def _institution(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "aicte_code": row["aicte_code"],
        "name": row["name"],
        "state": row["state"],
        "parent_trust": row["parent_trust"],
        "integrity_score": None,  # filled by Dev A's integrity pipeline later
    }


def list_institutions(conn: psycopg.Connection, user: User) -> list[dict[str, Any]]:
    only = scoped_institution(user)
    rows = conn.execute(
        "select * from public.institutions where %s::uuid is null or id = %s::uuid"
        " order by aicte_code",
        (only, only),
    ).fetchall()
    return [_institution(r) for r in rows]


def get_institution(conn: psycopg.Connection, institution_id: str, user: User) -> dict[str, Any]:
    scoped_institution(user, institution_id)
    row = (
        conn.execute(
            "select * from public.institutions where id = %s", (institution_id,)
        ).fetchone()
        if as_uuid(institution_id)
        else None
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Institution '{institution_id}' not found")
    programmes = conn.execute(
        "select id, code, name, level, duration_years from public.programmes"
        " where institution_id = %s order by code",
        (institution_id,),
    ).fetchall()
    return {**_institution(row), "programmes": [{**p, "id": str(p["id"])} for p in programmes]}


def create_api_key(conn: psycopg.Connection, institution_id: str, user: User) -> dict[str, Any]:
    """Generate a key, store only its SHA-256 hash, return the key once."""
    get_institution(conn, institution_id, user)
    key = "apaar_" + secrets.token_urlsafe(32)
    row = conn.execute(
        "insert into public.api_keys (institution_id, key_hash) values (%s, %s)"
        " returning id, created_at",
        (institution_id, hashlib.sha256(key.encode()).hexdigest()),
    ).fetchone()
    audit_store.append_event(
        conn, user.id, "api_key.created", "api_key", row["id"], {"institution_id": institution_id}
    )
    return {
        "key_id": str(row["id"]),
        "institution_id": institution_id,
        "api_key": key,
        "created_at": row["created_at"],
    }


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def api_key_user(conn: psycopg.Connection, key: str) -> User:
    """The institution_operator an X-API-Key stands for. Unknown or revoked keys are 401."""
    row = conn.execute(
        "select id, institution_id, revoked_at from public.api_keys where key_hash = %s",
        (hash_key(key),),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    if row["revoked_at"] is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has been revoked")
    return User(
        id=f"api_key:{row['id']}",
        role="institution_operator",
        institution_id=str(row["institution_id"]),
        display_name="Integration API key",
    )


def revoke_api_key(
    conn: psycopg.Connection, institution_id: str, key_id: str, user: User
) -> dict[str, Any]:
    """Revoke a key of this institution. Revoking twice keeps the first revocation time."""
    get_institution(conn, institution_id, user)
    row = (
        conn.execute(
            "select id, revoked_at from public.api_keys where id = %s and institution_id = %s"
            " for update",
            (key_id, institution_id),
        ).fetchone()
        if as_uuid(key_id)
        else None
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"API key '{key_id}' not found")
    if row["revoked_at"] is None:
        row = conn.execute(
            "update public.api_keys set revoked_at = now() where id = %s returning id, revoked_at",
            (key_id,),
        ).fetchone()
        audit_store.append_event(
            conn,
            user.id,
            "api_key.revoked",
            "api_key",
            row["id"],
            {"institution_id": institution_id},
        )
    return {
        "key_id": str(row["id"]),
        "institution_id": institution_id,
        "revoked_at": row["revoked_at"],
    }


def set_webhook(
    conn: psycopg.Connection, institution_id: str, url: str | None, user: User, signing_key: str
) -> dict[str, Any]:
    """Set (or clear, with None) the outbound webhook URL. A new secret is returned once."""
    get_institution(conn, institution_id, user)
    if url and not signing_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "WEBHOOK_SIGNING_KEY or PSEUDONYM_SECRET must be set to sign webhooks",
        )
    key_id = secrets.token_hex(8) if url else None
    conn.execute(
        "update public.institutions set webhook_url = %s, webhook_key_id = %s where id = %s",
        (url, key_id, institution_id),
    )
    audit_store.append_event(
        conn,
        user.id,
        "institution.webhook_set" if url else "institution.webhook_cleared",
        "institution",
        institution_id,
        {"webhook_key_id": key_id},
    )
    return {
        "institution_id": institution_id,
        "webhook_url": url,
        "secret": outbound_webhooks.secret_for(signing_key, institution_id, key_id)
        if key_id
        else None,
    }


def webhook_target(
    conn: psycopg.Connection, institution_id: str, signing_key: str
) -> tuple[str, str] | None:
    """(url, secret) when the institution has a webhook and signing is configured."""
    row = conn.execute(
        "select webhook_url, webhook_key_id from public.institutions where id = %s",
        (institution_id,),
    ).fetchone()
    if not row or not row["webhook_url"] or not row["webhook_key_id"] or not signing_key:
        return None
    return row["webhook_url"], outbound_webhooks.secret_for(
        signing_key, institution_id, row["webhook_key_id"]
    )
