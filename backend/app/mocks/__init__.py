# Owner: Dev B
"""JSON fixtures served for every domain that is not listed in REAL_DOMAINS."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

MOCK_DIR = Path(__file__).parent


@cache
def _read(name: str) -> Any:
    return json.loads((MOCK_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load(name: str) -> Any:
    """Return a deep copy of fixture ``<name>.json`` so callers can modify it freely."""
    return copy.deepcopy(_read(name))


def require_mock() -> None:
    """No-op. Unimplemented domains now fall back to fixtures instead of returning 501.

    Kept because routers owned by other devs still call it.
    """


def mock(name: str) -> Any:
    return load(name)


def not_found(what: str, key: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} '{key}' not found")
