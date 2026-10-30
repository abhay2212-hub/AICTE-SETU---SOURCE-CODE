# Owner: Dev B
"""Per-domain switch between mock fixtures and Postgres, reported in the X-Mock header."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from app.core.config import DOMAINS, get_settings


def all_real() -> bool:
    return get_settings().real_domain_set == frozenset(DOMAINS)


def mark_source(request: Request, real: bool) -> None:
    """Record where this response's data came from; the middleware turns it into X-Mock."""
    request.state.x_mock = "false" if real else "true"


def source(domain: str) -> Callable[[Request], bool]:
    """Dependency returning True when ``domain`` is served from Postgres."""

    def dependency(request: Request) -> bool:
        real = get_settings().is_real(domain)
        mark_source(request, real)
        return real

    return dependency
