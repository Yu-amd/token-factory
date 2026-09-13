"""AIM catalog loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from token_factory.runtime.paths import catalog_path


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    path = path or catalog_path()
    if not path.exists():
        raise FileNotFoundError(f"AIM catalog not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError("AIM catalog root must be a mapping")
    return data


def find_aim(catalog: dict[str, Any], model: str) -> dict[str, Any] | None:
    for aim in catalog.get("aims", []):
        if aim.get("model") == model:
            return aim
    return None


def support_level_for(
    aim: dict[str, Any],
    family: str,
    accelerator: str,
) -> str | None:
    family_data = aim.get("support", {}).get(family, {})
    return family_data.get(accelerator)
