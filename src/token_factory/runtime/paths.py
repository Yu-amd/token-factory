"""Runtime path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    return Path(os.environ.get("TF_CONFIG_DIR", repo_root() / "config"))


def generated_dir() -> Path:
    return Path(os.environ.get("TF_GENERATED_DIR", repo_root() / "generated"))


def runtime_dir() -> Path:
    override = os.environ.get("TF_RUNTIME_DIR")
    if override:
        return Path(override)
    cache = Path.home() / ".cache" / "token-factory" / "runtime"
    local = repo_root() / ".token-factory" / "runtime"
    return local if (repo_root() / ".token-factory").exists() or not cache.parent.exists() else cache


def catalog_path() -> Path:
    return repo_root() / "catalog" / "aims.yaml"


def policies_dir() -> Path:
    return repo_root() / "policies"
