# Owner: Dev B
import os

# Unit tests run with default settings even when backend/.env exists: mock auth, every domain
# on fixtures, no realtime calls. These env vars take precedence over backend/.env.
for _name, _value in {
    "MOCK_MODE": "true",
    "REAL_DOMAINS": "",
    "SUPABASE_URL": "",
    "SUPABASE_SERVICE_ROLE_KEY": "",
    "SUPABASE_JWT_SECRET": "",
    "TELEGRAM_WEBHOOK_SECRET": "",
    "INTERNAL_API_TOKEN": "",
    "WEBHOOK_SIGNING_KEY": "",
    # Blind Match is off unless a test passes a secret explicitly.
    "BLIND_MATCH_SECRET": "",
    "MATCH_THRESHOLD": "0.85",
    "BLIND_MATCH_MAX_BLOCK": "200",
}.items():
    os.environ[_name] = _value
# Unit runs never touch Postgres; DATABASE_URL from backend/.env is used only for the
# integration tests (RUN_DB_TESTS=1).
if os.environ.get("RUN_DB_TESTS") != "1":
    os.environ["DATABASE_URL"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def fake_blind_match(monkeypatch):
    """Replace the stub encoder with a contract-following fake (tests/fake_engine.py)."""
    import engine.blind_match.encoder as encoder

    from tests import fake_engine

    monkeypatch.setattr(encoder, "encode_identity", fake_engine.encode_identity)


@pytest.fixture
def settings_override():
    """Temporarily change cached settings, e.g. settings_override(mock_mode=False)."""
    settings = get_settings()
    saved = settings.model_dump()

    def apply(**values):
        for key, value in values.items():
            setattr(settings, key, value)

    yield apply
    for key, value in saved.items():
        setattr(settings, key, value)


def as_role(role: str, institution: str | None = None) -> dict[str, str]:
    headers = {"X-Demo-Role": role}
    if institution:
        headers["X-Demo-Institution"] = institution
    return headers
