"""YAML config loaders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from token_factory.runtime.paths import config_dir, repo_root


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def resolve_config_path(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute():
        return candidate
    for base in (config_dir(), repo_root() / "config", repo_root()):
        path = base / name
        if path.exists():
            return path
    return config_dir() / name


def load_endpoints(path: Path | None = None) -> dict[str, Any]:
    path = path or resolve_config_path("endpoints.yaml")
    if not path.exists():
        path = resolve_config_path("endpoints.example.yaml")
    return load_yaml(path)


def load_policies(path: Path | None = None) -> dict[str, Any]:
    path = path or resolve_config_path("policies.yaml")
    if not path.exists():
        path = resolve_config_path("policies.example.yaml")
    return load_yaml(path)


def load_token_factory(path: Path | None = None) -> dict[str, Any]:
    path = path or resolve_config_path("token-factory.yaml")
    if not path.exists():
        path = resolve_config_path("token-factory.example.yaml")
    return load_yaml(path)


def load_policy_profile(name: str) -> dict[str, Any]:
    policies_path = repo_root() / "policies" / f"{name}.yaml"
    if not policies_path.exists():
        raise FileNotFoundError(f"Policy profile not found: {policies_path}")
    return load_yaml(policies_path)
