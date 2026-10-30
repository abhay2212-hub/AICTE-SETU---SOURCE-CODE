# Owner: Dev B
"""Ed25519-signed student credentials with per-audience pseudonyms (shared/credentials.md).

The pure functions (canonical bytes, pseudonym, sign, decode, verify) need no database and
are what the test vectors in shared/test-vectors.json are generated from. The functions
taking a connection store issued credentials, revocations and access-log entries.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from fastapi import HTTPException, status
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey
from psycopg.types.json import Jsonb

from app.services import audit_store
from app.services.batches import as_uuid

VERSION = 1
ISSUER = "apaar-integrity-platform"
CLAIMS = ("enrolment_status", "institution", "programme", "academic_year")
EXPIRY = {
    "15m": timedelta(minutes=15),
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
}
# Internal only (enrolment certificates); the student API still accepts just EXPIRY's keys.
CERTIFICATE_EXPIRY = "180d"
_LIFETIMES = {**EXPIRY, CERTIFICATE_EXPIRY: timedelta(days=180)}
# Fixed seed for unit tests, test vectors and fixture mode. Never the production key.
TEST_SEED_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
TEST_PSEUDONYM_SECRET = "test-pseudonym-secret"
VERIFY_PURPOSE = "credential verification"


# ---------------------------------------------------------------------------- pure helpers
def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Sorted keys, compact separators, UTF-8 (non-ASCII kept as is)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def normalise_audience(audience: str) -> str:
    return " ".join(audience.split()).lower()


def pseudonym(secret: str, student_id: str, audience: str) -> str:
    message = f"{student_id}:{normalise_audience(audience)}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def signing_key(seed_hex: str) -> SigningKey:
    try:
        seed = bytes.fromhex(seed_hex)
    except ValueError:
        seed = b""
    if len(seed) != 32:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CREDENTIAL_SIGNING_KEY must be a 32-byte Ed25519 seed in hex",
        )
    return SigningKey(seed)


def public_key_b64(key: SigningKey) -> str:
    return base64.b64encode(bytes(key.verify_key)).decode()


def key_id(key: SigningKey) -> str:
    return hashlib.sha256(bytes(key.verify_key)).hexdigest()[:16]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def build_payload(
    *,
    student_id: str,
    audience: str,
    claims: dict[str, str],
    expiry: str,
    pseudonym_secret: str,
    now: datetime | None = None,
    credential_id: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    issued = int((now or datetime.now(UTC)).timestamp())
    return {
        "v": VERSION,
        "id": credential_id or str(uuid.uuid4()),
        "iss": ISSUER,
        "sub": pseudonym(pseudonym_secret, student_id, audience),
        "aud": audience,
        "claims": claims,
        "iat": issued,
        "exp": issued + int(_LIFETIMES[expiry].total_seconds()),
        "nonce": nonce or secrets.token_hex(16),
    }


def sign(payload: dict[str, Any], key: SigningKey) -> str:
    """QR text: base64url (no padding) of the UTF-8 JSON {"payload": ..., "sig": ...}."""
    signature = key.sign(canonical_bytes(payload)).signature
    envelope = {"payload": payload, "sig": base64.b64encode(signature).decode()}
    return _b64url(json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode())


def decode(qr_text: str) -> tuple[dict[str, Any], bytes] | None:
    """(payload, signature) or None when the text is not a credential."""
    try:
        envelope = json.loads(_b64url_decode(qr_text.strip()).decode("utf-8"))
        payload, signature = envelope["payload"], base64.b64decode(envelope["sig"], validate=True)
    except (ValueError, KeyError, TypeError, binascii.Error):
        return None
    if not isinstance(payload, dict) or len(signature) != 64:
        return None
    return payload, signature


def check(
    qr_text: str, verify_key: VerifyKey, revoked: set[str], now: datetime | None = None
) -> dict[str, Any]:
    """Signature, version, expiry, then revocation. Returns the verification result plus
    ``_payload`` (the signed payload, or None) for the caller's access log."""
    decoded = decode(qr_text)
    if decoded is None:
        return {"valid": False, "reason": "malformed", "_payload": None}
    payload, signature = decoded
    try:
        verify_key.verify(canonical_bytes(payload), signature)
    except BadSignatureError:
        return {"valid": False, "reason": "bad_signature", "_payload": None}
    if payload.get("v") != VERSION or payload.get("iss") != ISSUER:
        return {"valid": False, "reason": "unsupported", "_payload": None}
    expires = datetime.fromtimestamp(int(payload["exp"]), UTC)
    result: dict[str, Any] = {"valid": False, "expires_at": expires, "_payload": payload}
    if (now or datetime.now(UTC)) >= expires:
        return {**result, "reason": "expired"}
    if str(payload.get("id")) in revoked:
        return {**result, "reason": "revoked"}
    return {**result, "valid": True, "claims": payload.get("claims") or {}}


# ---------------------------------------------------------------------------- database
def _admission(
    conn: psycopg.Connection, student_id: str, admission_id: str | None
) -> dict[str, Any]:
    if admission_id is not None and as_uuid(admission_id) is None:
        admission_id = "00000000-0000-0000-0000-000000000000"
    row = conn.execute(
        """
        select a.id, a.status::text as status, a.academic_year, p.name as programme,
               i.name as institution
        from public.admissions a
        join public.programmes p on p.id = a.programme_id
        join public.institutions i on i.id = p.institution_id
        where a.student_id = %s and a.active and (%s::uuid is null or a.id = %s::uuid)
        order by a.created_at desc limit 1
        """,
        (student_id, admission_id, admission_id),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "NO_ACTIVE_ADMISSION", "message": "No active admission to share"},
        )
    return row


def claim_values(admission: dict[str, Any], names: list[str]) -> dict[str, str]:
    values = {
        "enrolment_status": admission["status"],
        "institution": admission["institution"],
        "programme": admission["programme"],
        "academic_year": admission["academic_year"],
    }
    return {name: str(values[name]) for name in CLAIMS if name in names}


def log_access(
    conn: psycopg.Connection,
    student_id: str,
    accessor: str,
    role: str,
    purpose: str,
    fields: list[str],
) -> None:
    conn.execute(
        """
        insert into public.access_log (student_id, accessor, accessor_role, purpose, fields)
        values (%s, %s, %s::public.app_role, %s, %s)
        """,
        (student_id, accessor, role, purpose, fields),
    )


def store(
    conn: psycopg.Connection, payload: dict[str, Any], student_id: str, admission_id: str
) -> datetime:
    """Record an issued credential so it can be revoked and its checks logged.
    Returns its expiry."""
    expires_at = datetime.fromtimestamp(payload["exp"], UTC)
    conn.execute(
        """
        insert into public.credentials
          (id, student_id, admission_id, audience, pseudonym, claims, issued_at, expires_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payload["id"],
            student_id,
            admission_id,
            payload["aud"],
            payload["sub"],
            Jsonb(payload["claims"]),
            datetime.fromtimestamp(payload["iat"], UTC),
            expires_at,
        ),
    )
    return expires_at


def issue(
    conn: psycopg.Connection,
    student_id: str,
    request: dict[str, Any],
    seed_hex: str,
    pseudonym_secret: str,
) -> dict[str, Any]:
    if not pseudonym_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PSEUDONYM_SECRET is not set")
    key = signing_key(seed_hex)
    admission = _admission(conn, student_id, request.get("admission_id"))
    claims = claim_values(admission, request["claims"])
    payload = build_payload(
        student_id=student_id,
        audience=request["audience"],
        claims=claims,
        expiry=request["expiry"],
        pseudonym_secret=pseudonym_secret,
    )
    qr_text = sign(payload, key)
    expires_at = store(conn, payload, student_id, str(admission["id"]))
    audit_store.append_event(
        conn,
        f"student:{student_id}",
        "credential.issued",
        "credential",
        payload["id"],
        {"audience": payload["aud"], "claims": sorted(claims), "expiry": request["expiry"]},
    )
    log_access(
        conn,
        student_id,
        "Student portal",
        "student",
        f"credential issued for {payload['aud']}",
        sorted(claims),
    )
    return credential_out(payload["id"], qr_text, expires_at, claims)


def credential_out(
    credential_id: str, qr_text: str, expires_at: datetime, claims: dict[str, str]
) -> dict[str, Any]:
    return {
        "id": credential_id,
        "qr_text": qr_text,
        "expires_at": expires_at,
        "claims": claims,
        "credential_id": credential_id,
        "qr_payload": qr_text,
    }


def revoke(
    conn: psycopg.Connection, student_id: str, credential_id: str, reason: str
) -> dict[str, Any]:
    owned = (
        conn.execute(
            "select id from public.credentials where id = %s and student_id = %s",
            (credential_id, student_id),
        ).fetchone()
        if as_uuid(credential_id)
        else None
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Credential '{credential_id}' not found")
    inserted = conn.execute(
        """
        insert into public.credential_revocations (credential_id, student_id, reason)
        values (%s, %s, %s) on conflict (credential_id) do nothing returning credential_id
        """,
        (credential_id, student_id, reason),
    ).fetchone()
    if inserted:
        audit_store.append_event(
            conn, f"student:{student_id}", "credential.revoked", "credential", credential_id, {}
        )
    row = conn.execute(
        "select credential_id, reason, revoked_at from public.credential_revocations"
        " where credential_id = %s",
        (credential_id,),
    ).fetchone()
    return {**row, "credential_id": str(row["credential_id"])}


def revocations(conn: psycopg.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "select credential_id, reason, revoked_at from public.credential_revocations"
        " order by revoked_at desc"
    ).fetchall()
    return {
        "updated_at": datetime.now(UTC),
        "revoked": [{**r, "credential_id": str(r["credential_id"])} for r in rows],
    }


def verify(conn: psycopg.Connection, qr_text: str, seed_hex: str) -> dict[str, Any]:
    """Check signature, expiry and revocation, and log the check for the student."""
    verify_key = signing_key(seed_hex).verify_key
    decoded = decode(qr_text)
    credential_id = str(decoded[0].get("id")) if decoded else None
    revoked: set[str] = set()
    if credential_id and as_uuid(credential_id):
        found = conn.execute(
            "select 1 from public.credential_revocations where credential_id = %s",
            (credential_id,),
        ).fetchone()
        if found:
            revoked.add(credential_id)
    result = check(qr_text, verify_key, revoked)
    payload = result.pop("_payload")
    if payload is not None and as_uuid(credential_id):
        owner = conn.execute(
            "select student_id from public.credentials where id = %s", (credential_id,)
        ).fetchone()
        if owner:
            log_access(
                conn,
                str(owner["student_id"]),
                str(payload.get("aud"))[:200],
                "verifier",
                VERIFY_PURPOSE,
                sorted(payload.get("claims") or {}),
            )
    return result
