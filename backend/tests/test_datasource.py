# Owner: Dev B
"""Per-domain switch, X-Mock header, health db status and best-effort realtime."""

import httpx
import pytest

from app.core.config import DOMAINS, Settings
from app.services import realtime
from tests.conftest import as_role

SHADOW = "10000000-0000-4000-8000-000000000003"


def test_real_domains_parsing():
    s = Settings(_env_file=None, real_domains=" batches, audit ,")
    assert s.real_domain_set == {"batches", "audit"}
    assert s.is_real("audit") and not s.is_real("institutions")
    assert Settings(_env_file=None).real_domain_set == frozenset()


def test_reports_and_certificates_domains():
    s = Settings(_env_file=None, real_domains="reports,certificates")
    assert s.real_domain_set == {"reports", "certificates"}
    assert s.is_real("reports") and s.is_real("certificates")
    unlisted = Settings(_env_file=None, real_domains="batches")
    assert not unlisted.is_real("reports") and not unlisted.is_real("certificates")
    assert not Settings(_env_file=None).is_real("reports")


def test_unknown_real_domain_rejected():
    with pytest.raises(ValueError):
        _ = Settings(_env_file=None, real_domains="batches,telegram").real_domain_set


def test_defaults():
    s = Settings(_env_file=None)
    assert (s.max_upload_mb, s.max_upload_rows, s.shared_contact_threshold) == (5, 20000, 5)
    assert s.admission_cutoff_date.isoformat() == "2026-09-30"


def test_fixture_domains_report_mock(client):
    response = client.get("/review-cases")
    assert response.headers["X-Mock"] == "true"


def test_real_domain_without_database_is_503_and_not_mock(client, settings_override):
    settings_override(real_domains="review_cases", database_url="")
    response = client.get("/review-cases")
    assert response.status_code == 503
    assert response.headers["X-Mock"] == "false"
    # Other domains keep serving fixtures.
    other = client.get(f"/institutions/{SHADOW}")
    assert other.status_code == 200 and other.headers["X-Mock"] == "true"


def test_non_domain_endpoints_follow_all_real(client, settings_override):
    assert client.get("/health").headers["X-Mock"] == "true"
    settings_override(real_domains=",".join(DOMAINS), database_url="")
    assert client.get("/health").headers["X-Mock"] == "false"


def test_health_reports_db_status(client, settings_override):
    settings_override(database_url="")
    body = client.get("/health").json()
    assert body["db"] == "unconfigured"
    assert body["real_domains"] == []


def test_mock_mode_false_still_serves_fixtures_for_dev_e(client, settings_override):
    import jwt

    secret = "hs256-secret-that-is-at-least-32-bytes"
    settings_override(mock_mode=False, supabase_jwt_secret=secret)
    token = jwt.encode(
        {"sub": "u1", "aud": "authenticated", "app_metadata": {"role": "verifier"}},
        secret,
        algorithm="HS256",
    )
    response = client.get("/credentials/public-key", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_upload_rejects_large_file_in_mock_mode(client, settings_override):
    settings_override(max_upload_mb=1)
    response = client.post(
        "/batches",
        files={"file": ("a.csv", b"x" * (1024 * 1024 + 1), "text/csv")},
        headers=as_role("institution_admin", SHADOW),
    )
    assert response.status_code == 413


def test_realtime_skips_when_unconfigured(settings_override):
    settings_override(supabase_url="", supabase_service_role_key="")
    assert realtime.publish([("batch.committed", {"batch_id": "b"})]) is False


def test_realtime_posts_broadcast(settings_override, monkeypatch):
    settings_override(supabase_url="https://ref.supabase.co", supabase_service_role_key="srk")
    sent = {}

    def fake_post(url, json, headers, timeout):
        sent.update(url=url, json=json, headers=headers, timeout=timeout)
        return httpx.Response(202, request=httpx.Request("POST", url))

    monkeypatch.setattr(realtime.httpx, "post", fake_post)
    assert realtime.publish([("batch.committed", {"batch_id": "b"})]) is True
    assert sent["url"] == "https://ref.supabase.co/realtime/v1/api/broadcast"
    assert sent["headers"]["apikey"] == "srk"
    assert sent["timeout"] == 2.0
    assert sent["json"] == {
        "messages": [
            {"topic": "platform", "event": "batch.committed", "payload": {"batch_id": "b"}}
        ]
    }


def test_realtime_failure_is_swallowed(settings_override, monkeypatch):
    settings_override(supabase_url="https://ref.supabase.co", supabase_service_role_key="srk")

    def boom(*args, **kwargs):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(realtime.httpx, "post", boom)
    assert realtime.publish([("batch.committed", {})]) is False
