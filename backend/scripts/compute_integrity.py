# Owner: Dev A
"""Compute job scoring institutions for an academic year and storing results via integrity_store.

Run from backend/:
    uv run python -m scripts.compute_integrity
    uv run python -m scripts.compute_integrity --year 2026-27
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import engine  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "src"))

from app.core.config import get_settings
from app.core.db import close_pool, transaction
from app.services.integrity import compute_institution_results
from app.services.integrity_store import save_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute and persist institution integrity scores."
    )
    parser.add_argument("--year", default="2026-27", help="Academic year (default 2026-27)")
    parser.add_argument(
        "--institutions",
        nargs="*",
        default=None,
        help="Optional list of institution UUIDs to compute scores for",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL must be set in backend/.env", file=sys.stderr)
        return 2

    with transaction() as conn:
        results = compute_institution_results(
            conn, academic_year=args.year, institution_ids=args.institutions
        )
        saved = save_results(conn, results)
        print(f"Computed integrity scores for {len(results)} institutions; persisted {saved} rows.")

    close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(main())
