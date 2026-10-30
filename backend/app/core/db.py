# Owner: Dev B
"""Postgres connection pool, created lazily so the app starts without DATABASE_URL."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from fastapi import HTTPException, status
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    """Return the shared pool, opening it on first use. Sized for the Supabase session pooler."""
    global _pool
    url = get_settings().database_url
    if not url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_URL is not configured")
    if _pool is None:
        with _lock:
            if _pool is None:
                pool = ConnectionPool(
                    url,
                    min_size=1,
                    max_size=5,
                    kwargs={"row_factory": dict_row, "prepare_threshold": None},
                    open=False,
                )
                pool.open(wait=False)
                _pool = pool
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """A pooled connection inside one transaction: commit on success, roll back on error."""
    with get_pool().connection() as conn, conn.transaction():
        yield conn


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: one transaction per request."""
    with transaction() as conn:
        yield conn


# Opening a TLS connection to the Supabase pooler can itself take 2-3 seconds, so getting a
# connection has its own allowance; the 2-second limit applies to the query.
CONNECT_TIMEOUT_SECONDS = 5
HEALTH_QUERY_TIMEOUT_MS = 2000


def warm_pool() -> None:
    """Start opening connections in the background so the first request is not slow."""
    if get_settings().database_url:
        get_pool()


def check_db() -> str:
    """'ok', 'unconfigured' or 'error'. Never raises."""
    if not get_settings().database_url:
        return "unconfigured"
    try:
        with get_pool().connection(timeout=CONNECT_TIMEOUT_SECONDS) as conn:
            conn.execute(f"set local statement_timeout = {HEALTH_QUERY_TIMEOUT_MS}")
            conn.execute("select 1")
        return "ok"
    except Exception:  # noqa: BLE001
        return "error"
