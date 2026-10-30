<!-- Owner: Dev B -->
# backend

FastAPI service for the APAAR Integrity Platform.

```sh
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
uv run pytest
uv run ruff check .
uv run python -m scripts.export_contracts           # writes ../shared/openapi.json and ../shared/schemas/
```

## Data sources and auth

Two independent switches:

- `REAL_DOMAINS` (comma-separated, default empty) picks which domains come from Postgres: `institutions`, `seat_ledger`, `batches`, `admissions`, `review_cases`, `audit`, `submission_windows`, `blind_match`, `students`, `credentials`, `integrity`, `reports`, `certificates`. Every other domain serves fixtures from `app/mocks/`. Dev C's `reports` and `certificates` serve fixtures unless listed in `REAL_DOMAINS`. Responses carry `X-Mock: true` for fixtures and `X-Mock: false` for Postgres.
- `MOCK_MODE` controls auth only. `true` (default): the user comes from `X-Demo-Role` (`institution_admin`, `institution_operator`, `aicte_admin` (default), `student`, `verifier`, `auditor`) and `X-Demo-Institution`. `false`: a Supabase access token, verified against the project JWKS (ES256/RS256) or `SUPABASE_JWT_SECRET` (HS256), reading `app_metadata.role` and `app_metadata.institution_id`.

Institution users only ever see and write their own institution's rows; `aicte_admin` and `auditor` see everything.

Real domains need `DATABASE_URL` (Supabase session pooler URI) and `PSEUDONYM_SECRET` (contact hashing) in `backend/.env`. `/health` reports `db: ok | unconfigured | error`.

## Pipeline

`POST /batches` (CSV or XLSX, at most `MAX_UPLOAD_MB` and `MAX_UPLOAD_ROWS`) → suggested header mapping (synonyms such as `apaar_no`, `mobile`, `date_of_birth`) → `POST /batches/{id}/mapping` if required columns are missing → validation against `shared/rule-codes.md` → `POST /batches/{id}/commit`. Commit is one transaction: students upserted, seat pools locked, admissions inserted, one `intake_overrun` case per overrun pool, one `signal` case per cross-institution duplicate, audit events chained. Re-uploading the same file or re-committing is idempotent. Phone numbers and emails are HMAC-hashed on arrival and never stored raw.

Realtime events (`shared/events.md`) go to the Supabase Broadcast channel `platform` when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set; failures are logged and ignored. Frontend usage: `shared/realtime-client.md`.

## Windows, corrections and responses

- **Submission windows** (`/submission-windows`, set and locked by `aicte_admin`): uploads and commits for an academic year are allowed only while its window is open. Outside it they return 409 with `detail.code = SUBMISSION_WINDOW_CLOSED`. A year with no window is not restricted. After a window closes or is locked, admission changes go through edit requests (`POST /admissions/{id}/edit-requests`, decided at `POST /edit-requests/{id}/decision`). The field `withdrawal` withdraws the admission on approval.
- **Withdrawals:** `POST /admissions/{id}/withdraw` (`institution_admin`, reason required) releases the seat. If the pool is back within capacity, a note is added to its open overrun case.
- **Corrections:** `POST /batches/{id}/corrections` re-uploads the rejected rows of a committed batch and commits only those, as a child batch (`parent_batch_id`).
- **Findings:** `POST /validation-issues/{id}/resolve` with a note. Warnings and info: institution or AICTE admin. Review findings: `aicte_admin`. Errors are fixed with corrections.
- **Student responses:** `POST /internal/student-responses` (`X-Internal-Token`), contract in `shared/student-responses.md`. `POST /admin/admissions/mark-no-response` (`aicte_admin`).
- **Integration:** `X-API-Key` on `POST /batches`, `/batches/{id}/commit` and `/corrections`, key revocation, and a signed `batch.committed` webhook. See `shared/integration-api.md`.

## Tests

```sh
uv run pytest -q                                     # unit tests; never touch the database
RUN_DB_TESTS=1 uv run pytest tests/integration -q    # against DATABASE_URL; TEST- rows, cleaned up afterwards
```

## Demo dataset and realtime probe

```sh
uv run python -m scripts.load_demo --reset --yes     # see scripts/README.md
uv run python -m scripts.realtime_probe --seconds 60 # print every broadcast on `platform`
```

## Audit tamper demo

```sh
uv run python -m scripts.tamper_demo --break --yes   # GET /audit/verify now fails at that event
uv run python -m scripts.tamper_demo --restore --yes
```

## Layout

| Path | Purpose | Owner |
| --- | --- | --- |
| `app/main.py` | App, CORS, `X-Mock` middleware, routers | Dev B |
| `app/core/` | Settings, auth, audit hash chain, rule codes | Dev B |
| `app/models/` | Pydantic v2 models, one file per domain (the contract) | Dev B |
| `app/routers/engine.py`, `integrity.py`, `blind_match.py` | Engine, Integrity and Blind Match endpoints | Dev A |
| `app/routers/reports.py`, `certificates.py` | Reports and certificates | Dev C |
| `app/routers/credentials.py`, `students.py`, `webhooks.py` | Student side | Dev E |
| other `app/routers/` | Everything else | Dev B |
| `app/core/db.py`, `datasource.py` | Postgres pool and the per-domain switch | Dev B |
| `app/services/` | Ingestion, validation, batches, Seat Ledger, admissions, review cases, audit store, realtime; other files are placeholders | Dev B |
| `app/mocks/` | Fixtures. Ids follow `<prefix>-0000-4000-8000-<n>`: `1…` institutions, `2…` programmes, `3…` batches, `4…` students, `5…` admissions, `6…` review cases | Dev B |

Demo identities: "Shadow Institute of Technology" is `10000000-0000-4000-8000-000000000003`; the demo student is `40000000-0000-4000-8000-000000000001`. The mock credential is signed with a demo Ed25519 key derived from a public string, so it is for mock mode only.

After changing a model or endpoint, run the contract export and then `npm run gen:api` in `frontend/`.
