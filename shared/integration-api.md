<!-- Owner: Dev B -->
# Integration API: system-to-system uploads

An institution's ERP or admissions system can upload and commit admissions without a person logging in. It authenticates with an **institution API key** and can receive a signed **`batch.committed` webhook** after each commit.

## 1. Get a key

An `institution_admin` of that institution (or an `aicte_admin`) creates a key:

```
POST /institutions/{institution_id}/api-keys
```

```json
{
  "key_id": "93000000-0000-4000-8000-000000000001",
  "institution_id": "10000000-0000-4000-8000-000000000001",
  "api_key": "apaar_....",
  "created_at": "2026-09-01T08:00:00Z",
  "note": "Shown once. Only a hash is stored."
}
```

The key is shown once. The platform stores only its SHA-256 hash.

- **Scope:** the key acts as an `institution_operator` of its own institution only. A batch of another institution returns 403. Rows naming another institution's AICTE code are rejected with `PROGRAMME_UNKNOWN`.
- **Audit:** every event the key causes records `actor = api_key:<key_id>`.
- **Revoke:** `POST /institutions/{institution_id}/api-keys/{key_id}/revoke`. From then on the key gets 401. Revoking twice keeps the first revocation time.

## 2. Upload

Send the key in `X-API-Key` instead of a bearer token. Use the headers of `shared/csv/admissions-template.csv`. With them the batch is mapped and validated straight away.

```powershell
$key = "apaar_replace-with-your-key"
curl.exe -s -X POST "https://<api-host>/batches" `
  -H "X-API-Key: $key" `
  -F "file=@admissions-2026-27.csv;type=text/csv"
```

The reply is `201` with `batch.id`, `batch.status` (`validated`) and `batch.counts` (rows with errors, warnings, review and info findings). The same file again returns `200` with `duplicate_upload: true` and the existing batch. Findings: `GET /batches/{id}/issues` (user auth).

## 3. Commit

```powershell
curl.exe -s -X POST "https://<api-host>/batches/<batch_id>/commit" -H "X-API-Key: $key"
```

```json
{
  "batch_id": "30000000-0000-4000-8000-000000000001",
  "status": "committed",
  "rows_committed": 71,
  "rows_rejected": 4,
  "rows_skipped_existing": 0,
  "review_cases_created": ["60000000-0000-4000-8000-000000000001"],
  "parent_batch_id": null,
  "rows_not_matched": 0
}
```

Rows with an error finding are not committed. Commit is idempotent: committing again returns the same result.

To fix rejected rows later, upload a file with only those rows, corrected, to `POST /batches/{batch_id}/corrections` (also accepts `X-API-Key`). Add a `source_row` column with the original row number to match rows exactly. Without it, rows match by APAAR ID, provisional ID, or name and date of birth.

## Errors

| HTTP | When |
| --- | --- |
| 401 | `X-API-Key` unknown or revoked |
| 403 | The batch belongs to another institution |
| 409 `detail.code = SUBMISSION_WINDOW_CLOSED` | The academic year's submission window is not open (not yet open, closed, or locked by AICTE). `detail` also has `academic_year`, `state` and `message`. |
| 409 | Commit of a batch that is not validated yet |
| 413 / 415 / 422 | File too large / not CSV or XLSX / unreadable or too many rows |

## 4. Webhook: `batch.committed`

An `institution_admin` sets the URL that receives commits:

```powershell
curl.exe -s -X PUT "https://<api-host>/institutions/<institution_id>/webhook" `
  -H "Authorization: Bearer <institution admin token>" `
  -H "Content-Type: application/json" `
  --data-raw '{\"url\":\"https://erp.example.edu/apaar/webhook\"}'
```

The reply contains `secret` (`whsec_...`), **shown once**. Setting the URL again rotates the secret. `{"url": null}` removes the webhook.

After every commit (uploads, API-key commits and corrections), the platform sends:

```
POST <webhook_url>
Content-Type: application/json
X-Event: batch.committed
X-Signature: sha256=<hex HMAC-SHA256 of the raw body, keyed with the secret>

{"event":"batch.committed","payload":{"batch_id":"...","institution_id":"...","rows_committed":71,"rows_rejected":4,"committed_at":"2026-09-02T10:15:00+00:00"}}
```

Delivery is best effort: one attempt, 3-second timeout. A failed delivery never fails the commit. Reply with any 2xx. The payload has IDs and counts only, so fetch the details with your key or a user token.

### Verifying the signature

Compute the HMAC over the **raw request body bytes** (not re-serialised JSON) and compare in constant time.

PowerShell:

```powershell
$secret = "whsec_replace-with-your-secret"
$body = [System.IO.File]::ReadAllBytes("body.json")      # the raw body you received
$hmac = [System.Security.Cryptography.HMACSHA256]::new([Text.Encoding]::UTF8.GetBytes($secret))
$expected = "sha256=" + (($hmac.ComputeHash($body) | ForEach-Object { $_.ToString("x2") }) -join "")
$expected -eq $receivedSignature
```

Python:

```python
import hashlib, hmac

def valid(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

To test a receiver by hand, sign a sample body and post it:

```powershell
$payload = '{"event":"batch.committed","payload":{"batch_id":"test"}}'
$sig = "sha256=" + (($hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($payload)) | ForEach-Object { $_.ToString("x2") }) -join "")
curl.exe -s -X POST "http://localhost:9000/apaar/webhook" -H "Content-Type: application/json" `
  -H "X-Event: batch.committed" -H "X-Signature: $sig" --data-raw $payload
```

## Mock mode

While the `batches` domain is on fixtures (not in `REAL_DOMAINS`), only the fixture key `apaar_demo_k3y_not_a_real_secret_0001` (Meghdoot Institute) is accepted and nothing is stored.
