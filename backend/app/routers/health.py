# Owner: Dev B
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.db import check_db
from app.models.health import Health

router = APIRouter(tags=["health"])

APP_VERSION = "0.1.0"


@router.get("/health", response_model=Health)
def health(settings: Settings = Depends(get_settings)) -> Health:
    try:
        import engine

        engine_ok, engine_version = True, getattr(engine, "__version__", None)
    except ImportError:
        engine_ok, engine_version = False, None
    return Health(
        status="ok",
        mock_mode=settings.mock_mode,
        engine_import_ok=engine_ok,
        engine_version=engine_version,
        version=APP_VERSION,
        db=check_db(),
        real_domains=sorted(settings.real_domain_set),
    )
