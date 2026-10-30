# Owner: Dev B
"""Demo: break the audit hash chain on purpose, then put it back.

    uv run python -m scripts.tamper_demo --break --yes [--event-id N]
    uv run python -m scripts.tamper_demo --restore --yes

--break edits one audit event's payload directly in the database (bypassing the API) and
saves the original to backend/scripts/.tamper_backup.json. GET /audit/verify then reports
the event's position as first_broken_index. --restore writes the original back.
Uses DATABASE_URL from backend/.env; never prints it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.config import get_settings

BACKUP = Path(__file__).with_name(".tamper_backup.json")


def connect() -> psycopg.Connection:
    url = get_settings().database_url
    if not url:
        sys.exit("DATABASE_URL is not configured in backend/.env")
    return psycopg.connect(url, row_factory=dict_row, prepare_threshold=None)


def break_chain(conn: psycopg.Connection, event_id: int | None) -> tuple[int, int]:
    """Tamper with one event; return (event id, its index in the chain)."""
    if BACKUP.exists():
        sys.exit(f"{BACKUP.name} already exists; run --restore first")
    if event_id is None:
        row = conn.execute(
            "select id from public.audit_events order by id"
            " offset (select count(*) / 2 from public.audit_events) limit 1"
        ).fetchone()
        if row is None:
            sys.exit("The audit log is empty; nothing to tamper with")
        event_id = row["id"]
    event = conn.execute(
        "select id, payload from public.audit_events where id = %s", (event_id,)
    ).fetchone()
    if event is None:
        sys.exit(f"No audit event with id {event_id}")
    index = conn.execute(
        "select count(*) as n from public.audit_events where id < %s", (event_id,)
    ).fetchone()["n"]
    BACKUP.write_text(json.dumps({"id": event_id, "payload": event["payload"]}), encoding="utf-8")
    conn.execute(
        "update public.audit_events set payload = payload || '{\"tampered\": true}'::jsonb"
        " where id = %s",
        (event_id,),
    )
    conn.commit()
    return event_id, index


def restore(conn: psycopg.Connection) -> int:
    if not BACKUP.exists():
        sys.exit(f"No {BACKUP.name}; nothing to restore")
    saved = json.loads(BACKUP.read_text(encoding="utf-8"))
    conn.execute(
        "update public.audit_events set payload = %s where id = %s",
        (Jsonb(saved["payload"]), saved["id"]),
    )
    conn.commit()
    BACKUP.unlink()
    return saved["id"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Break or restore the audit chain (demo).")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--break", dest="do_break", action="store_true")
    action.add_argument("--restore", action="store_true")
    parser.add_argument("--event-id", type=int, help="event to tamper with (default: middle)")
    parser.add_argument("--yes", action="store_true", help="confirm writing to the database")
    args = parser.parse_args(argv)
    if not args.yes:
        sys.exit("Refusing to run without --yes: this writes directly to the audit log.")
    with connect() as conn:
        if args.do_break:
            event_id, index = break_chain(conn, args.event_id)
            print(f"Tampered audit event id={event_id} (chain index {index}).")
            print("GET /audit/verify should now report first_broken_index =", index)
        else:
            print(f"Restored audit event id={restore(conn)}.")


if __name__ == "__main__":
    main()
