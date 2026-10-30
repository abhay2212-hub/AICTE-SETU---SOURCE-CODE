# Owner: Dev B
"""Subscribe to the Supabase Realtime broadcast channel `platform` and print every event.

Run from backend/ (needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env), then
commit a batch from another terminal or the UI:

    uv run python -m scripts.realtime_probe --seconds 60

Prints one JSON line per event and a count per event name on exit. Exit code 1 when a name
given with --expect did not arrive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import UTC, datetime

from realtime import AsyncRealtimeClient, RealtimeSubscribeStates

from app.core.config import get_settings
from app.services.realtime import CHANNEL

# shared/events.md. The Python client has no wildcard listener, so every name is registered.
EVENTS = (
    "batch.committed",
    "review_case.created",
    "review_case.updated",
    "admission.status_changed",
    "audit.tamper_detected",
    "submission_window.updated",
    "edit_request.decided",
)


async def probe(seconds: float) -> Counter[str]:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in backend/.env")
    client = AsyncRealtimeClient(
        f"{settings.supabase_url.rstrip('/')}/realtime/v1",
        token=settings.supabase_service_role_key,
        auto_reconnect=False,
    )
    seen: Counter[str] = Counter()
    joined = asyncio.Event()

    def on_event(message: dict) -> None:
        seen[message["event"]] += 1
        line = {
            "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "event": message["event"],
            "payload": message.get("payload", {}),
        }
        print(json.dumps(line), flush=True)

    def on_state(state: RealtimeSubscribeStates, error: Exception | None) -> None:
        if state == RealtimeSubscribeStates.SUBSCRIBED:
            print(f"Subscribed to '{CHANNEL}' for {seconds:.0f} s", flush=True)
            joined.set()
        elif error is not None:
            print(f"Channel state {state}: {error}", file=sys.stderr, flush=True)

    await client.connect()
    channel = client.channel(CHANNEL)
    for name in EVENTS:
        channel.on_broadcast(name, on_event)
    await channel.subscribe(on_state)
    try:
        await asyncio.wait_for(joined.wait(), timeout=15)
        await asyncio.sleep(seconds)
    finally:
        await client.close()
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument(
        "--expect", nargs="*", default=[], help="Event names that must arrive, e.g. batch.committed"
    )
    args = parser.parse_args(argv)
    seen = asyncio.run(probe(args.seconds))
    print("Received:", json.dumps(dict(sorted(seen.items()))) if seen else "nothing", flush=True)
    missing = [name for name in args.expect if not seen[name]]
    if missing:
        print(f"Missing: {missing}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
