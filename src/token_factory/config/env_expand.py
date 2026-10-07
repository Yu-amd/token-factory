"""Expand ${VAR} and ${VAR:-default} placeholders in config structures."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_PATTERN = re.compile(
    r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}"
)


def expand_string(value: str, env: dict[str, str] | None = None) -> str:
    environ = env if env is not None else os.environ

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        if key in environ and environ[key] != "":
            return environ[key]
        if default is not None:
            return default
        return match.group(0)  # leave unresolved for validators to catch

    return _ENV_PATTERN.sub(repl, value)


def expand_value(value: Any, env: dict[str, str] | None = None) -> Any:
    if isinstance(value, str):
        return expand_string(value, env)
    if isinstance(value, list):
        return [expand_value(v, env) for v in value]
    if isinstance(value, dict):
        return {k: expand_value(v, env) for k, v in value.items()}
    return value


def unresolved_placeholders(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.extend(_ENV_PATTERN.findall(value) and [m[0] for m in _ENV_PATTERN.findall(value) if f"${{{m[0]}" in value or True])
        # simpler: any remaining ${VAR} without default applied
        for m in re.finditer(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value):
            found.append(m.group(1))
    elif isinstance(value, list):
        for v in value:
            found.extend(unresolved_placeholders(v))
    elif isinstance(value, dict):
        for v in value.values():
            found.extend(unresolved_placeholders(v))
    return found
