# Owner: Dev B
"""Cross-institution Blind Match rescan over every committed student. Changes no data except
encodings for students that have none and new blind_match review cases; safe to rerun (a
student pair never gets a second case). Run from backend/:

    uv run python -m scripts.blind_match_scan
"""

from __future__ import annotations

import sys

from app.core.config import get_settings
from app.core.db import close_pool, transaction
from app.services import blind_match, realtime


def main() -> int:
    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL must be set in backend/.env")
        return 2
    if not settings.blind_match_secret:
        print("BLIND_MATCH_SECRET is empty; nothing to do")
        return 2
    with transaction() as conn:
        result = blind_match.scan_all(conn)
        total = conn.execute(
            "select count(*) as n from public.review_cases where kind = 'blind_match'"
        ).fetchone()["n"]
    realtime.publish(result.pop("events", []))
    close_pool()
    print(f"students encoded     {result['students_encoded']}")
    print(f"candidates compared  {result['candidates']}")
    print(f"matches at or above  {result['matches']}  (threshold {settings.match_threshold})")
    print(f"new cases            {len(result['cases_created'])}")
    print(f"blind_match cases    {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
