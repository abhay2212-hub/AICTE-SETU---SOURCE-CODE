# Owner: Dev B
"""Supabase token verification with locally generated keys; no network."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException

from app.core import security
from app.core.config import Settings
from app.core.security import _user_from_jwt, scoped_institution
from app.models.auth import User

URL = "https://example-ref.supabase.co"
ISSUER = f"{URL}/auth/v1"
HS_SECRET = "hs256-secret-that-is-at-least-32-bytes"


def claims(**overrides):
    base = {
        "sub": "11111111-1111-4111-8111-111111111111",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": int(time.time()) + 600,
        "email": "admin@example.com",
        "app_metadata": {"role": "institution_admin", "institution_id": "inst-1"},
    }
    return {**base, **overrides}


class FakeJWKClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return type("Key", (), {"key": self.public_key})()


@pytest.fixture(params=["ES256", "RS256"])
def signer(request, monkeypatch):
    if request.param == "ES256":
        private = ec.generate_private_key(ec.SECP256R1())
    else:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(security, "jwks_client", lambda url: FakeJWKClient(private.public_key()))
    return lambda payload: jwt.encode(
        payload, private, algorithm=request.param, headers={"kid": "k1"}
    )


def bearer(token: str) -> str:
    return f"Bearer {token}"


def test_asymmetric_token_accepted(signer):
    user = _user_from_jwt(bearer(signer(claims())), Settings(_env_file=None, supabase_url=URL))
    assert user.role == "institution_admin"
    assert user.institution_id == "inst-1"
    assert user.demo is False


@pytest.mark.parametrize(
    "bad",
    [
        {"aud": "anon"},
        {"iss": "https://evil.example/auth/v1"},
        {"exp": int(time.time()) - 10},
    ],
)
def test_asymmetric_token_rejected(signer, bad):
    with pytest.raises(HTTPException) as err:
        _user_from_jwt(bearer(signer(claims(**bad))), Settings(_env_file=None, supabase_url=URL))
    assert err.value.status_code == 401


def test_missing_role_is_403(signer):
    token = signer(claims(app_metadata={}))
    with pytest.raises(HTTPException) as err:
        _user_from_jwt(bearer(token), Settings(_env_file=None, supabase_url=URL))
    assert err.value.status_code == 403


def test_hs256_fallback_with_secret():
    token = jwt.encode(claims(), HS_SECRET, algorithm="HS256")
    user = _user_from_jwt(
        bearer(token), Settings(_env_file=None, supabase_url=URL, supabase_jwt_secret=HS_SECRET)
    )
    assert user.role == "institution_admin"


def test_hs256_rejected_without_secret():
    token = jwt.encode(claims(), HS_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as err:
        _user_from_jwt(bearer(token), Settings(_env_file=None, supabase_url=URL))
    assert err.value.status_code == 401


def test_hs256_wrong_issuer_rejected():
    token = jwt.encode(claims(iss="https://other.supabase.co/auth/v1"), HS_SECRET, "HS256")
    with pytest.raises(HTTPException):
        _user_from_jwt(
            bearer(token), Settings(_env_file=None, supabase_url=URL, supabase_jwt_secret=HS_SECRET)
        )


def test_unsupported_algorithm_rejected():
    token = jwt.encode(claims(), HS_SECRET, algorithm="HS512")
    with pytest.raises(HTTPException) as err:
        _user_from_jwt(
            bearer(token), Settings(_env_file=None, supabase_url=URL, supabase_jwt_secret=HS_SECRET)
        )
    assert err.value.status_code == 401


def test_missing_bearer():
    with pytest.raises(HTTPException) as err:
        _user_from_jwt(None, Settings(_env_file=None, supabase_url=URL))
    assert err.value.status_code == 401


# ---------------------------------------------------------------- institution scoping
def user(role, institution=None):
    return User(id="u", role=role, institution_id=institution)


def test_institution_user_pinned_to_own_institution():
    assert scoped_institution(user("institution_admin", "A")) == "A"
    assert scoped_institution(user("institution_operator", "A"), "A") == "A"


@pytest.mark.parametrize("role", ["institution_admin", "institution_operator"])
def test_institution_user_cannot_reach_other_institution(role):
    with pytest.raises(HTTPException) as err:
        scoped_institution(user(role, "A"), "B")
    assert err.value.status_code == 403


def test_institution_user_without_institution_is_403():
    with pytest.raises(HTTPException) as err:
        scoped_institution(user("institution_admin"))
    assert err.value.status_code == 403


@pytest.mark.parametrize("role", ["aicte_admin", "auditor"])
def test_aicte_and_auditor_see_everything(role):
    assert scoped_institution(user(role)) is None
    assert scoped_institution(user(role), "B") == "B"
