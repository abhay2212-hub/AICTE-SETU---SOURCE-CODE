# Owner: Dev B (contract: shared/credentials.md)
from __future__ import annotations

from datetime import datetime
from typing import Literal, get_args

from pydantic import BaseModel, Field, model_validator

ClaimName = Literal["enrolment_status", "institution", "programme", "academic_year"]
Expiry = Literal["15m", "1d", "7d"]

# Deprecated request names from the first student page, mapped to the new ones.
_LEGACY_CLAIMS = {"status": "enrolment_status"}
_LEGACY_EXPIRY = {1: "1d", 7: "7d"}


class CredentialRequest(BaseModel):
    claims: list[ClaimName] | None = Field(None, description="Claims to share (at least one)")
    audience: str | None = Field(
        None, max_length=200, description="Verifier the credential is for, e.g. 'Acme Infotech'"
    )
    expiry: Expiry | None = None
    admission_id: str | None = Field(
        None, description="Admission to describe; default the student's most recent active one"
    )
    verifier_id: str | None = Field(None, description="Deprecated: use audience")
    purpose: str | None = Field(None, description="Deprecated: ignored")
    fields: list[str] | None = Field(None, description="Deprecated: use claims")
    expires_in_days: int | None = Field(None, description="Deprecated: use expiry (1 or 7)")

    @model_validator(mode="after")
    def _resolve(self) -> CredentialRequest:
        if self.audience is None and self.verifier_id:
            self.audience = self.verifier_id
        if self.claims is None and self.fields is not None:
            names = [_LEGACY_CLAIMS.get(f, f) for f in self.fields]
            unknown = sorted(set(names) - set(get_args(ClaimName)))
            if unknown:
                raise ValueError(f"claims not allowed: {unknown}")
            self.claims = names
        if self.expiry is None and self.expires_in_days is not None:
            if self.expires_in_days not in _LEGACY_EXPIRY:
                raise ValueError("expires_in_days must be 1 or 7; use expiry")
            self.expiry = _LEGACY_EXPIRY[self.expires_in_days]
        self.audience = (self.audience or "").strip() or None
        if not self.audience:
            raise ValueError("audience is required")
        if not self.claims:
            raise ValueError("choose at least one claim")
        if self.expiry is None:
            raise ValueError("expiry is required: 15m, 1d or 7d")
        self.claims = list(dict.fromkeys(self.claims))
        return self


class Credential(BaseModel):
    id: str
    qr_text: str = Field(description="base64url JSON {payload, sig}; see shared/credentials.md")
    expires_at: datetime
    claims: dict[str, str]
    credential_id: str = Field(description="Deprecated: same as id")
    qr_payload: str = Field(description="Deprecated: same as qr_text")


class RevokeRequest(BaseModel):
    reason: str = Field(min_length=1)


class Revocation(BaseModel):
    credential_id: str
    reason: str
    revoked_at: datetime


class RevocationList(BaseModel):
    updated_at: datetime
    revoked: list[Revocation]


class PublicKey(BaseModel):
    algorithm: Literal["Ed25519"] = "Ed25519"
    key_id: str
    public_key_b64: str = Field(description="Standard base64 of the raw 32-byte public key")


class VerifyRequest(BaseModel):
    qr_text: str = Field(min_length=1, max_length=8192)


class Verification(BaseModel):
    valid: bool
    reason: Literal["malformed", "bad_signature", "unsupported", "expired", "revoked"] | None = None
    claims: dict[str, str] | None = None
    expires_at: datetime | None = None
