"""YAML config loaders."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from token_factory.config.env_expand import expand_value
from token_factory.runtime.paths import config_dir, repo_root


def _load_dotenv() -> None:
    """Best-effort load of repo-root /.env into os.environ (does not override)."""
    try:
        env_path = repo_root() / ".env"
        if not env_path.exists():
            return
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def load_yaml(path: Path, *, expand_env: bool = True) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    if expand_env:
        _load_dotenv()
        data = expand_value(data)
        # Coerce endpoint ports back to int when expanded from env strings
        for ep in data.get("endpoints") or []:
            if isinstance(ep, dict) and "port" in ep:
                try:
                    ep["port"] = int(ep["port"])
                except (TypeError, ValueError):
                    pass
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


def load_execution_targets(path: Path | None = None) -> dict[str, Any]:
    """Load Phase 1/2 execution_targets + adapter registry (example if missing)."""
    path = path or resolve_config_path("execution-targets.yaml")
    if not path.exists():
        path = resolve_config_path("execution-targets.example.yaml")
    if not path.exists():
        return {"version": "2", "execution_targets": [], "adapters": {}}
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
    """Load a V1/V2 profile overlay — prefers policies/profiles/, falls back to policies/."""
    name = name.removesuffix(".yaml")
    root = repo_root()
    candidates = [
        root / "policies" / "profiles" / f"{name}.yaml",
        root / "policies" / f"{name}.yaml",
    ]
    for policies_path in candidates:
        if policies_path.exists():
            return load_yaml(policies_path)
    raise FileNotFoundError(
        f"Policy profile not found: {name} (searched {[str(c) for c in candidates]})"
    )
