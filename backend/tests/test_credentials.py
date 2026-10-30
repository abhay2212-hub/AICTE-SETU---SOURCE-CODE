# Owner: Dev B
"""Credential format (shared/credentials.md), test vectors and the fixture-mode endpoints."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services import credentials as cred
from tests.conftest import as_role

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "shared" / "test-vectors.json").read_text("utf-8")
)["credentials"]
KEY = cred.signing_key(cred.TEST_SEED_HEX)
STUDENT = "40000000-0000-4000-8000-000000000001"


def envelope(qr_text: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(qr_text + "=" * (-len(qr_text) % 4)))


def at(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


def payload(**overrides):
    base = cred.build_payload(
        student_id=STUDENT,
        audience="Acme Infotech",
        claims={"programme": "B.Tech CSE", "institution": "Meghdoot"},
        expiry="1d",
        pseudonym_secret="s",
        now=datetime(2026, 9, 10, tzinfo=UTC),
        credential_id="92000000-0000-4000-8000-000000000009",
        nonce="ab" * 16,
    )
    return {**base, **overrides}


def test_canonical_bytes_are_stable():
    p = payload()
    shuffled = dict(reversed(list(p.items())))
    assert cred.canonical_bytes(p) == cred.canonical_bytes(shuffled)
    assert (
        cred.canonical_bytes({"b": 1, "a": {"d": "é", "c": 2}})
        == '{"a":{"c":2,"d":"é"},"b":1}'.encode()
    )


def test_vectors_match_canonical_bytes_and_public_key():
    assert VECTORS["public_key_b64"] == cred.public_key_b64(KEY)
    assert VECTORS["key_id"] == cred.key_id(KEY)
    for case in VECTORS["cases"]:
        assert cred.canonical_bytes(case["payload"]).decode() == case["canonical_payload"]


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_vectors_verify_as_expected(case):
    result = cred.check(
        case["qr_text"], KEY.verify_key, set(case["revoked_ids"]), at(case["verify_at"])
    )
    result.pop("_payload")
    expect = case["expect"]
    assert result["valid"] is expect["valid"]
    assert result.get("reason") == expect.get("reason")
    if "expires_at" in expect:
        assert result["expires_at"] == at(expect["expires_at"])
    if expect["valid"]:
        assert result["claims"] == expect["claims"]


def test_vectors_regenerate_identically():
    from scripts.credential_vectors import build

    assert build() == VECTORS


def test_tampered_payload_fails():
    qr = cred.sign(payload(), KEY)
    env = envelope(qr)
    env["payload"]["claims"]["programme"] = "MBBS"
    forged = base64.urlsafe_b64encode(json.dumps(env).encode()).decode()
    assert cred.check(forged, KEY.verify_key, set())["reason"] == "bad_signature"


def test_other_key_fails():
    other = cred.signing_key("11" * 32)
    qr = cred.sign(payload(), other)
    assert cred.check(qr, KEY.verify_key, set())["reason"] == "bad_signature"


def test_expired_and_revoked_fail():
    p = payload()
    qr = cred.sign(p, KEY)
    assert cred.check(qr, KEY.verify_key, set(), at(p["exp"] - 1))["valid"] is True
    assert cred.check(qr, KEY.verify_key, set(), at(p["exp"]))["reason"] == "expired"
    assert cred.check(qr, KEY.verify_key, {p["id"]}, at(p["iat"]))["reason"] == "revoked"


@pytest.mark.parametrize("text", ["", "not base64 !!", base64.urlsafe_b64encode(b"{}").decode()])
def test_malformed_fails(text):
    assert cred.check(text, KEY.verify_key, set())["reason"] == "malformed"


def test_expiry_choices():
    for expiry, seconds in (("15m", 900), ("1d", 86400), ("7d", 604800)):
        p = payload() | cred.build_payload(
            student_id=STUDENT, audience="x", claims={}, expiry=expiry, pseudonym_secret="s"
        )
        assert p["exp"] - p["iat"] == seconds


def test_pseudonym_differs_per_audience_and_ignores_spacing_and_case():
    one = cred.pseudonym("secret", STUDENT, "Acme Infotech")
    assert one == cred.pseudonym("secret", STUDENT, "  acme   INFOTECH ")
    assert one != cred.pseudonym("secret", STUDENT, "Merit Scholarship Cell")
    assert one != cred.pseudonym("secret", "40000000-0000-4000-8000-000000000002", "Acme Infotech")
    assert len(one) == 64


def test_claims_only_from_the_allowed_set():
    admission = {
        "status": "student_confirmed",
        "institution": "Meghdoot",
        "programme": "B.Tech CSE",
        "academic_year": "2026-27",
        "apaar_id": "999912340001",
    }
    claims = cred.claim_values(admission, ["programme", "apaar_id", "enrolment_status"])
    assert claims == {"enrolment_status": "student_confirmed", "programme": "B.Tech CSE"}


# ---------------------------------------------------------------------------- endpoints
def issue(client, **body):
    request = {"claims": ["enrolment_status", "institution"], "audience": "Acme", "expiry": "1d"}
    return client.post("/credentials", json=request | body, headers=as_role("student"))


def test_issue_and_verify_in_fixture_mode(client):
    response = issue(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body["claims"]) == {"enrolment_status", "institution"}
    assert body["credential_id"] == body["id"] and body["qr_payload"] == body["qr_text"]
    p = envelope(body["qr_text"])["payload"]
    assert (p["v"], p["iss"], p["aud"]) == (1, "apaar-integrity-platform", "Acme")
    assert set(p) == {"v", "id", "iss", "sub", "aud", "claims", "iat", "exp", "nonce"}

    verified = client.post("/credentials/verify", json={"qr_text": body["qr_text"]})
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["claims"] == body["claims"]

    env = envelope(body["qr_text"])
    env["payload"]["aud"] = "Someone else"
    forged = base64.urlsafe_b64encode(json.dumps(env).encode()).decode()
    bad = client.post("/credentials/verify", json={"qr_text": forged}).json()
    assert bad == {"valid": False, "reason": "bad_signature"}


def test_apaar_never_in_qr_text(client):
    body = issue(
        client, claims=["enrolment_status", "institution", "programme", "academic_year"]
    ).json()
    decoded = json.dumps(envelope(body["qr_text"]))
    assert "999912340001" not in decoded
    assert "apaar_id" not in decoded and "XXXX" not in decoded


def test_apaar_claim_is_rejected(client):
    assert issue(client, claims=["apaar_id"]).status_code == 422
    legacy = {"verifier_id": "Acme", "fields": ["apaar_id"], "expires_in_days": 7}
    assert client.post("/credentials", json=legacy, headers=as_role("student")).status_code == 422


def test_legacy_request_names_still_work(client):
    legacy = {"verifier_id": "Acme", "purpose": "x", "fields": ["status"], "expires_in_days": 7}
    response = client.post("/credentials", json=legacy, headers=as_role("student"))
    assert response.status_code == 201, response.text
    p = envelope(response.json()["qr_text"])["payload"]
    assert list(p["claims"]) == ["enrolment_status"] and p["exp"] - p["iat"] == 7 * 86400
    bad_days = legacy | {"expires_in_days": 30}
    assert client.post("/credentials", json=bad_days, headers=as_role("student")).status_code == 422


def test_issue_needs_student_and_claims(client):
    assert issue(client, claims=[]).status_code == 422
    assert issue(client, audience="  ").status_code == 422
    assert issue(client, expiry="30d").status_code == 422
    other = client.post(
        "/credentials",
        json={"claims": ["programme"], "audience": "Acme", "expiry": "1d"},
        headers=as_role("verifier"),
    )
    assert other.status_code == 403


def test_public_endpoints_need_no_login(client):
    key = client.get("/credentials/public-key", headers={}).json()
    assert key["public_key_b64"] == VECTORS["public_key_b64"]
    assert client.get("/credentials/revocations").status_code == 200
    assert client.post("/credentials/verify", json={"qr_text": "x"}).json()["reason"] == "malformed"


def test_revoke_is_for_the_owning_student(client):
    path = "/credentials/92000000-0000-4000-8000-000000000001/revoke"
    assert (
        client.post(path, json={"reason": "x"}, headers=as_role("aicte_admin")).status_code == 403
    )
    ok = client.post(path, json={"reason": "Lost phone"}, headers=as_role("student"))
    assert ok.status_code == 200 and ok.json()["reason"] == "Lost phone"


@pytest.mark.parametrize("seed", ["", "abcd", "zz" * 32])
def test_signing_key_must_be_a_32_byte_hex_seed(seed):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        cred.signing_key(seed)
    assert err.value.status_code == 503
