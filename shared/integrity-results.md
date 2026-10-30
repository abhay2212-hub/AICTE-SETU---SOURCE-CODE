<!-- Owner: Dev B. Consumed by Dev A (engine compute job, backend/app/routers/integrity.py). Mirrored by backend/app/services/integrity_store.py. -->
# Integrity results

Dev A's compute job (`compute_integrity.py`) scores each institution for an academic year and stores the results with `app.services.integrity_store`. `routers/integrity.py` reads them back. The table is `public.integrity_scores` (migration `20261024100000_blind_match_students_credentials.sql`).

## Writing

```python
from app.core.db import transaction
from app.services.integrity_store import save_results

with transaction() as conn:
    save_results(conn, results)  # list[dict], shape below
```

- One row per `(institution_id, academic_year, model_version)`. Saving the same key again **replaces** score, tier, components, top_features, signals and computed_at (upsert). Running the job twice is safe.
- `save_results` runs inside the caller's transaction and returns the number of rows written. A dict missing a required key raises `ValueError` before anything is written.

## Result dict

```python
{
    "institution_id": "10000000-0000-4000-8000-000000000003",   # required, UUID string
    "academic_year": "2026-27",                                  # required, YYYY-YY
    "score": 41.5,                                               # required, number
    "tier": "high_risk",                                         # required, string
    "model_version": "0.1.0",                                    # required, string (settings.model_version)
    "components": {"anomaly": 0.82, "signals": 0.64, "seat_ledger": 0.9},  # optional, JSON object
    "top_features": [                                            # optional, JSON array
        {"feature": "cap_filling", "value": 1.18, "contribution": 0.31}
    ],
    "signals": [                                                 # optional, JSON array
        {"code": "INTAKE_OVERRUN", "count": 11, "severity": "review"}
    ],
    "computed_at": "2026-10-24T06:00:00Z",                       # optional, datetime; default now
}
```

| Key | Type | Notes |
| --- | --- | --- |
| `institution_id` | `str` | Must exist in `public.institutions`. Rows are deleted when the institution is. |
| `academic_year` | `str` | `YYYY-YY`, e.g. `2026-27`. |
| `score` | `int` or `float` | Stored as `numeric`; read back as `float`. Dev A defines the scale and direction. Document it in `routers/integrity.py`. |
| `tier` | `str` | Free text chosen by Dev A (e.g. `low_risk`, `watch`, `high_risk`). |
| `model_version` | `str` | Use `settings.model_version` so a model change writes new rows instead of overwriting old ones. |
| `components` | `dict` | Default `{}`. |
| `top_features` | `list` | Default `[]`. Used for the "why" explanation. |
| `signals` | `list` | Default `[]`. |
| `computed_at` | `datetime` or ISO string | Default: the time of the save. |

All JSON values must be JSON-serialisable (no `numpy` types: convert with `float()` / `int()`).

**Privacy**: results are per institution. Never put student names, dates of birth, contacts or APAAR IDs in `components`, `top_features` or `signals`. Use counts, rates and rule codes.

## Reading

```python
from app.services.integrity_store import latest_for

with transaction() as conn:
    row = latest_for(conn, institution_id, "2026-27")
```

Returns the row with the latest `computed_at` for that institution and year, across model versions, or `None`. Keys are the ones above. `institution_id` is a `str`, `score` a `float` and `computed_at` a timezone-aware `datetime`.
