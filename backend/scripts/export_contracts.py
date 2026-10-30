# Owner: Dev B
"""Write shared/openapi.json and one JSON Schema per public Pydantic model to shared/schemas/.

Run from backend/: uv run python -m scripts.export_contracts
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
from pathlib import Path

from pydantic import BaseModel

import app.models
from app.main import app as fastapi_app

SHARED = Path(__file__).resolve().parents[2] / "shared"


def _write(path: Path, data: dict) -> None:
    # newline="\n" keeps contracts LF on Windows too.
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def public_models() -> dict[str, type[BaseModel]]:
    models: dict[str, type[BaseModel]] = {}
    for info in pkgutil.iter_modules(app.models.__path__):
        module = importlib.import_module(f"app.models.{info.name}")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseModel)
                and obj.__module__ == module.__name__
                and not name.startswith("_")
            ):
                if name in models:
                    raise SystemExit(f"Duplicate model name {name} in {module.__name__}")
                models[name] = obj
    return models


def main() -> None:
    schemas = SHARED / "schemas"
    schemas.mkdir(parents=True, exist_ok=True)
    for stale in schemas.glob("*.json"):
        stale.unlink()
    _write(SHARED / "openapi.json", fastapi_app.openapi())
    models = public_models()
    for name, model in sorted(models.items()):
        _write(schemas / f"{name}.json", model.model_json_schema())
    print(f"Wrote {SHARED / 'openapi.json'} and {len(models)} schemas to {schemas}")


if __name__ == "__main__":
    main()
