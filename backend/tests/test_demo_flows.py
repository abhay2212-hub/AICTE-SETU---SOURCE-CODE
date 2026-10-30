# Owner: Dev B
"""Task 02 flows without a database: the scripted demo batches, submission windows,
corrections matching, webhook signatures, API keys and the internal endpoint."""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.config import Settings
from app.services import outbound_webhooks
from app.services.batches import match_corrections, source_rows, upload_years
from app.services.ingestion import (
    TEMPLATE_COLUMNS,
    ParsedUpload,
    normalize_rows,
    suggest_mapping,
)
from app.services.submission_windows import state
from app.services.validation import ValidationContext, error_rows, validate_rows
from scripts.load_demo import (
    MEGHDOOT,
    MEGHDOOT_PLAN,
    NARMADA,
    NARMADA_PLAN,
    SHADOW_STORY,
    Scripted,
    match_quality,
    scripted_typo_pairs,
    shadow_rows,
)
from tests.conftest import as_role

MEGHDOOT_ID = "10000000-0000-4000-8000-000000000001"
SHADOW_ID = "10000000-0000-4000-8000-000000000003"
FIXTURE_KEY = "apaar_demo_k3y_not_a_real_secret_0001"
SECRET = "unit-test-secret"


def _validate(rows, code, programmes, elsewhere=None):
    mapping = suggest_mapping(TEMPLATE_COLUMNS).mapping
    normalized = normalize_rows(rows, mapping, SECRET)
    ctx = ValidationContext(
        cutoff=date(2026, 9, 30),
        institution_code=code,
        programme_codes=programmes,
        cross_institution_lookup=(lambda ids: {i: "1-9999002" for i in ids if i in elsewhere})
        if elsewhere
        else None,
    )
    return normalized, validate_rows(normalized, ctx, blind_match_secret=SECRET)


@pytest.fixture
def demo(fake_blind_match):
    gen = Scripted(42, set())
    meghdoot = gen.clean(MEGHDOOT, MEGHDOOT_PLAN, block=1)
    narmada = gen.clean(NARMADA, NARMADA_PLAN, block=2)
    twins = [r for r in narmada if r["programme_code"] == "UG-CSE" and r["seat_pool"] == "regular"]
    return meghdoot, narmada, twins[3:5], shadow_rows(gen, twins[3:5], twins[5])


# ---------------------------------------------------------------------------- demo dataset
def test_shadow_batch_tells_the_story(demo):
    _, _, twins, shadow = demo
    rows, findings = _validate(
        shadow, "1-9999003", {"UG-CSE", "UG-CE"}, {t["apaar_id"] for t in twins}
    )
    by_code = Counter()
    for code in {f.rule_code.value for f in findings}:
        by_code[code] = len({f.row_number for f in findings if f.rule_code.value == code})
    errors = error_rows(findings)
    assert len(rows) == 75 and len(errors) == SHADOW_STORY["rejected"]
    assert by_code["SHARED_CONTACT_CLUSTER"] == SHADOW_STORY["contact_cluster"]
    assert by_code["ADMISSION_AFTER_CUTOFF"] == SHADOW_STORY["after_cutoff"]
    assert by_code["DUP_CROSS_INSTITUTION"] == SHADOW_STORY["cross_institution"]
    assert by_code["APAAR_OPTED_OUT"] == SHADOW_STORY["opted_out"]
    for code in ("REQUIRED_FIELD_MISSING", "APAAR_FORMAT", "PROGRAMME_UNKNOWN", "DATE_INVALID"):
        assert by_code[code] == 1
    # Nothing else fires: no other warnings and no other errors.
    expected = {
        "SHARED_CONTACT_CLUSTER", "ADMISSION_AFTER_CUTOFF", "DUP_CROSS_INSTITUTION",
        "APAAR_OPTED_OUT", "REQUIRED_FIELD_MISSING", "APAAR_FORMAT", "PROGRAMME_UNKNOWN",
        "DATE_INVALID",
    }  # fmt: skip
    assert set(by_code) == expected

    committed = [r for r in rows if r.row_number not in errors]
    pools = Counter(r.values["seat_pool"] for r in committed)
    assert len(committed) == SHADOW_STORY["admitted"]
    assert pools == {"regular": 62, "tfw": 3, "fn_oci_pio": 3, "nri": 3}
    # Seed seats: 51 regular + 3 + 3 + 3 = 60; only the regular pool runs over, by 11.
    assert pools["regular"] - 51 == SHADOW_STORY["overrun_by"]
    assert len(committed) - 60 == SHADOW_STORY["overrun_by"]


@pytest.mark.parametrize("which", ["meghdoot", "narmada"])
def test_seed_batches_are_clean(demo, which):
    meghdoot, narmada, _, _ = demo
    rows, code, programmes = {
        "meghdoot": (meghdoot, "1-9999001", {"UG-CSE", "UG-ME"}),
        "narmada": (narmada, "1-9999002", {"UG-CSE", "UG-ECE"}),
    }[which]
    _, findings = _validate(rows, code, programmes)
    assert findings == []


def test_scripted_apaars_avoid_source_ids():
    taken = {"999901000001", "999901000002"}
    gen = Scripted(1, taken)
    assert gen.apaar(1) == "999901000003"


# ---------------------------------------------------------------------------- windows
def test_window_states():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    window = {
        "opens_at": now - timedelta(days=10),
        "closes_at": now + timedelta(days=10),
        "locked_at": None,
    }
    assert state(window, now) == "open"
    assert state(window, now - timedelta(days=11)) == "not_open"
    assert state(window, now + timedelta(days=10)) == "closed"
    assert state({**window, "locked_at": now}, now) == "locked"


def test_upload_years_follow_the_mapping():
    rows = [{"Session": "2026-27"}, {"Session": " 2025-26 "}, {"Session": ""}]
    assert upload_years(rows, {"Session": "academic_year"}) == {"2026-27", "2025-26"}
    assert upload_years(rows, {}) == set()


def test_window_endpoints_in_mock_mode(client):
    listed = client.get("/submission-windows", headers=as_role("institution_operator"))
    assert listed.status_code == 200 and listed.json()[0]["academic_year"] == "2026-27"
    body = {
        "academic_year": "2027-28",
        "opens_at": "2027-07-01T00:00:00Z",
        "closes_at": "2027-10-31T00:00:00Z",
    }
    assert client.post("/submission-windows", json=body).status_code == 201
    denied = client.post("/submission-windows", json=body, headers=as_role("institution_admin"))
    assert denied.status_code == 403
    bad = client.post("/submission-windows", json={**body, "academic_year": "2027"})
    assert bad.status_code == 422
    window_id = listed.json()[0]["id"]
    locked = client.post(f"/submission-windows/{window_id}/lock")
    assert locked.status_code == 200 and locked.json()["state"] == "locked"


# ---------------------------------------------------------------------------- corrections
def test_match_corrections_by_source_row_then_identity():
    mapping = suggest_mapping(TEMPLATE_COLUMNS).mapping
    rejected = {
        4: {"apaar_id": "12345", "student_name": "Asha Rao", "dob": "2008-01-02"},
        9: {"apaar_id": "999900000009", "student_name": None, "dob": "2008-05-06"},
        12: {"apaar_id": "999900000012", "student_name": "Ravi Iyer", "dob": "2008-07-08"},
    }
    raw = [
        {**dict.fromkeys(TEMPLATE_COLUMNS, ""), "apaar_id": "999900000004",
         "student_name": "asha rao", "dob": "2008-01-02"},
        {**dict.fromkeys(TEMPLATE_COLUMNS, ""), "apaar_id": "999900000009",
         "student_name": "Kiran Das", "dob": "2008-05-06"},
        {**dict.fromkeys(TEMPLATE_COLUMNS, ""), "apaar_id": "999900000077",
         "student_name": "Nobody", "dob": "2008-01-01"},
    ]  # fmt: skip
    rows = normalize_rows(raw, mapping, SECRET)
    assert match_corrections(rejected, rows, {}) == {1: 4, 2: 9}
    # An explicit source_row wins, and each rejected row is matched at most once.
    assert match_corrections(rejected, rows, {3: 12, 1: 4, 2: 4}) == {1: 4, 3: 12}


def test_source_row_column():
    parsed = ParsedUpload(
        headers=["Source Row", "apaar_id"],
        rows=[{"Source Row": "12", "apaar_id": "x"}, {"Source Row": "n/a", "apaar_id": "y"}],
        file_hash="h",
    )
    assert source_rows(parsed) == {1: 12}


def test_corrections_endpoint_in_mock_mode(client):
    batch = "30000000-0000-4000-8000-000000000001"
    response = client.post(
        f"/batches/{batch}/corrections",
        files={"file": ("fix.csv", b"apaar_id\n999900000001\n", "text/csv")},
        headers=as_role("institution_admin", SHADOW_ID),
    )
    assert response.status_code == 200, response.text
    assert response.json()["parent_batch_id"] == batch


def test_resolve_issue_rules_in_mock_mode(client):
    path = "/validation-issues/{}/resolve"
    note = {"note": "Checked with the admission office."}
    admin = as_role("institution_admin", SHADOW_ID)
    assert client.post(path.format(1), json=note, headers=admin).status_code == 409  # error
    assert client.post(path.format(5), json=note, headers=admin).status_code == 403  # review
    assert client.post(path.format(5), json=note).status_code == 200  # aicte_admin
    ok = client.post(path.format(9), json=note, headers=admin)  # warning
    assert ok.status_code == 200 and ok.json()["resolved"] is True
    assert client.post(path.format(9), json={"note": ""}, headers=admin).status_code == 422
    assert client.post(path.format(9), json=note, headers=as_role("student")).status_code == 403


# ---------------------------------------------------------------------------- withdrawals
def test_withdraw_needs_institution_admin_and_reason(client):
    admission = "50000000-0000-4000-8000-000000000002"
    path = f"/admissions/{admission}/withdraw"
    admin = as_role("institution_admin", MEGHDOOT_ID)
    assert client.post(path, json={"reason": ""}, headers=admin).status_code == 422
    denied = client.post(path, json={"reason": "Left"}, headers=as_role("institution_operator"))
    assert denied.status_code == 403
    ok = client.post(path, json={"reason": "Student left for another college."}, headers=admin)
    assert ok.status_code == 200 and ok.json()["status"] == "withdrawn"


def test_withdrawal_is_an_edit_request_field(client):
    admission = "50000000-0000-4000-8000-000000000002"
    response = client.post(
        f"/admissions/{admission}/edit-requests",
        json={"field": "withdrawal", "new_value": "withdrawn", "reason": "Left after lock."},
        headers=as_role("institution_admin", MEGHDOOT_ID),
    )
    assert response.status_code == 201


# ---------------------------------------------------------------------------- student responses
def test_internal_endpoint_needs_token(client, settings_override):
    body = {
        "admission_id": "50000000-0000-4000-8000-000000000002",
        "response": "confirmed",
        "channel": "telegram",
    }
    assert client.post("/internal/student-responses", json=body).status_code == 503
    settings_override(telegram_webhook_secret="tg-secret")
    assert client.post("/internal/student-responses", json=body).status_code == 401
    wrong = client.post(
        "/internal/student-responses", json=body, headers={"X-Internal-Token": "nope"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"]["code"] == "INVALID_INTERNAL_TOKEN"
    ok = client.post(
        "/internal/student-responses", json=body, headers={"X-Internal-Token": "tg-secret"}
    )
    assert ok.status_code == 200
    assert ok.json() == {
        "admission_id": body["admission_id"],
        "status": "student_confirmed",
        "changed": True,
        "review_case_id": None,
    }
    settings_override(internal_api_token="internal-only")
    stale = client.post(
        "/internal/student-responses", json=body, headers={"X-Internal-Token": "tg-secret"}
    )
    assert stale.status_code == 401
    bad = client.post(
        "/internal/student-responses",
        json={**body, "response": "maybe"},
        headers={"X-Internal-Token": "internal-only"},
    )
    assert bad.status_code == 422


def test_mark_no_response_is_aicte_only(client):
    path = "/admin/admissions/mark-no-response"
    assert client.post(path, json={"older_than_days": 14}).status_code == 200
    denied = client.post(path, json={}, headers=as_role("institution_admin", MEGHDOOT_ID))
    assert denied.status_code == 403


def test_settings_fallbacks():
    s = Settings(_env_file=None, telegram_webhook_secret="t", pseudonym_secret="p")
    assert (s.internal_token, s.webhook_key) == ("t", "p")
    s = Settings(_env_file=None, internal_api_token="i", webhook_signing_key="w")
    assert (s.internal_token, s.webhook_key) == ("i", "w")
    assert Settings(_env_file=None, real_domains="submission_windows").is_real("submission_windows")


# ---------------------------------------------------------------------------- API keys
def test_api_key_upload_in_mock_mode(client):
    files = {"file": ("admissions.csv", b"Student Name,APAAR ID\nA,1\n", "text/csv")}
    ok = client.post("/batches", files=files, headers={"X-API-Key": FIXTURE_KEY})
    assert ok.status_code == 201
    assert ok.json()["batch"]["institution_id"] == MEGHDOOT_ID
    assert ok.json()["batch"]["uploaded_by"] == "api_key:93000000-0000-4000-8000-000000000001"
    bad = client.post("/batches", files=files, headers={"X-API-Key": "apaar_wrong"})
    assert bad.status_code == 401


def test_api_key_revoke_and_webhook_in_mock_mode(client):
    revoked = client.post(
        f"/institutions/{MEGHDOOT_ID}/api-keys/93000000-0000-4000-8000-000000000001/revoke"
    )
    assert revoked.status_code == 200 and revoked.json()["revoked_at"]
    hook = client.put(
        f"/institutions/{MEGHDOOT_ID}/webhook", json={"url": "https://erp.example.com/hook"}
    )
    assert hook.status_code == 200 and hook.json()["secret"]
    assert (
        client.put(f"/institutions/{MEGHDOOT_ID}/webhook", json={"url": "ftp://x"}).status_code
        == 422
    )


def test_webhook_signature_round_trip():
    secret = outbound_webhooks.secret_for("k", "inst-1", "key-1")
    assert secret.startswith("whsec_")
    assert secret != outbound_webhooks.secret_for("k", "inst-1", "key-2")
    body = outbound_webhooks.body_for("batch.committed", {"batch_id": "b1", "rows_committed": 3})
    import hashlib
    import hmac

    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert outbound_webhooks.sign(secret, body) == expected


def test_webhook_delivery_never_raises(monkeypatch):
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", boom)
    assert outbound_webhooks.deliver("https://x.example", "s", "batch.committed", {}) is False


def test_chains_keep_shared_apaar_jobs_together_and_in_order():
    from scripts.load_demo import chains

    jobs = [
        ("i1", "a", [{"apaar_id": "1"}, {"apaar_id": "2"}]),
        ("i2", "b", [{"apaar_id": "3"}]),
        ("i3", "c", [{"apaar_id": "2"}, {"apaar_id": ""}]),
        ("i4", "d", [{"apaar_id": "3"}, {"apaar_id": "4"}]),
        ("i5", "e", [{"apaar_id": "5"}]),
    ]
    names = sorted([j[1] for j in group] for group in chains(jobs))
    assert names == [["a", "c"], ["b", "d"], ["e"]]


def test_scripted_typo_pair_is_the_shadow_copy_of_narmada():
    gen = Scripted(42, set())
    narmada = gen.clean(NARMADA, NARMADA_PLAN, block=2)
    twins = [r for r in narmada if r["programme_code"] == "UG-CSE" and r["seat_pool"] == "regular"]
    shadow = shadow_rows(gen, twins[3:5], twins[5])
    pairs = scripted_typo_pairs(shadow, twins[5])
    assert len(pairs) == 1
    copy, source = pairs[0]
    assert source is twins[5]
    assert copy["apaar_id"] != source["apaar_id"]
    assert copy["guardian_name"] == source["guardian_name"]


def test_match_quality_counts_the_scripted_pair_as_a_true_case():
    planted = {f"p{i}" for i in range(12)}
    # Every planted pair found, the scripted pair found, plus one false case.
    cases = planted | {"shadow:narmada", "x:y"}
    quality = match_quality(planted, {"shadow:narmada"}, cases, 12, 1)
    assert (quality["planted_found"], quality["planted"]) == (12, 12)
    assert (quality["scripted_found"], quality["scripted"]) == (1, 1)
    assert (quality["cases"], quality["true_positives"]) == (14, 13)
    assert quality["precision"] == 13 / 14
    assert quality["recall"] == 1.0

    exact = match_quality(planted, {"shadow:narmada"}, planted | {"shadow:narmada"}, 12, 1)
    assert exact["precision"] == exact["recall"] == 1.0

    missed = match_quality(planted, {"shadow:narmada"}, {"p0", "p1"}, 12, 1)
    assert (missed["planted_found"], missed["scripted_found"]) == (2, 0)
    assert missed["precision"] == 1.0
    assert missed["recall"] == 2 / 13

    none = match_quality(set(), set(), set(), 0, 0)
    assert none["precision"] is None and none["recall"] is None
