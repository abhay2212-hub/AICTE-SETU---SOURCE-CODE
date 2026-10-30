<!-- Owner: Dev X -->
# Live demo: a late Shadow batch

`shadow-late-batch.csv` is a 3-row upload for Shadow Institute of Technology, UG-CSE 2026-27, in the upload template columns. All data is synthetic, and the APAAR IDs are SIMULATED.

| Row | Student | What it shows |
| --- | --- | --- |
| 1 | Ishita Saxena | clean row |
| 2 | Yash Tiwarii | a Narmada Valley CSE student (Yash Tiwari) with one letter misspelled, the same DOB and guardian, and a different valid APAAR ID |
| 3 | Kunal Verma | clean row |

All 3 rows pass validation with no findings, because the duplicate has its own valid APAAR ID. Only Blind Match catches it after the commit.

## Before the demo

1. Load the dataset with the default seed (row 2 matches a student that only seed 42 creates). From `backend/`:

   ```powershell
   uv run python -m scripts.load_demo --reset --yes
   ```

   The Shadow check should end with `overrun_by 11 ok` and `blind_match_with_narmada 1 ok`.
2. Start the backend with `BLIND_MATCH_SECRET` set and `blind_match` real (`MOCK_MODE=false`, or `blind_match` in `REAL_DOMAINS`). Otherwise the commit does not run Blind Match. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` so the commit is broadcast.
3. Open two windows: one as `institution_operator` of Shadow, one as `aicte_admin` on `/aicte`.

## Upload through the UI

1. In the role switcher pick **institution_operator**, institution **Shadow Institute of Technology** (`10000000-0000-4000-8000-000000000003`, the default).
2. Open `/institution` and upload `deck/demo/shadow-late-batch.csv`.
3. The columns map on their own. Validation shows **3 rows, 3 valid, 0 errors, 0 warnings**.
4. Click **Commit**. The result is 3 committed, 0 rejected.

## What appears live on the AICTE screen

With no reload:

- **batch.committed**: Shadow, 3 rows committed.
- **intake_overrun case updated**: the Shadow UG-CSE regular pool goes from 62 admitted against 51 seats (over by 11) to **65 against 51 (over by 14)**. The programme is now 74 against 60. It is the same case, refreshed, not a new one.
- **New blind_match case**: Shadow and Narmada Valley, matched on name, DOB and guardian, dice about 0.98. It also shows on `/blindmatch`. The institution side sees only its own record; the other side is hidden.

No signal case opens, because no APAAR ID is shared with another institution.

## Reset after the demo

From `backend/`:

```powershell
uv run python -m scripts.demo_live_reset          # shows what it would remove, changes nothing
uv run python -m scripts.demo_live_reset --yes    # removes it
```

This removes only what the file added: its batch (with rows and findings), its 3 admissions, the 3 students it created, and the Blind Match case it opened. The overrun case goes back to over by 11. Audit events are kept, and one `demo_reset` event is appended, so `/audit/verify` still passes. You can then upload the file again.
