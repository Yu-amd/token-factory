"""Scenario pack schema helpers and soft validation."""

from __future__ import annotations

from typing import Any

REQUIRED_PACK_KEYS = ("id", "display_name", "scenarios")
REQUIRED_SCENARIO_KEYS = ("id", "request")

KNOWN_INJECTIONS = frozenset(
    {
        "preferred-endpoint-unavailable",
        "no-radeon",
        "no-epyc",
        "no-local",
        "no-instinct",
        "lifecycle-restriction",
    }
)

KNOWN_TRAFFIC = frozenset({"sequential", "low", "medium", "high", "light", "mixed"})


class ScenarioSchemaError(ValueError):
    """Raised when a scenario pack fails schema checks."""


def validate_pack(doc: dict[str, Any], *, pack_id: str | None = None) -> list[str]:
    """Return a list of schema errors (empty = valid)."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["pack root must be a mapping"]
    for key in REQUIRED_PACK_KEYS:
        if key not in doc:
            errors.append(f"missing pack key: {key}")
    if pack_id and doc.get("id") and doc["id"] != pack_id:
        errors.append(f"pack id '{doc.get('id')}' does not match filename stem '{pack_id}'")
    scenarios = doc.get("scenarios")
    if scenarios is None:
        return errors
    if not isinstance(scenarios, list) or not scenarios:
        errors.append("scenarios must be a non-empty list")
        return errors
    seen: set[str] = set()
    for i, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            errors.append(f"scenarios[{i}] must be a mapping")
            continue
        for key in REQUIRED_SCENARIO_KEYS:
            if key not in sc:
                errors.append(f"scenarios[{i}] missing key: {key}")
        sid = sc.get("id")
        if sid in seen:
            errors.append(f"duplicate scenario id: {sid}")
        if sid:
            seen.add(sid)
        req = sc.get("request") or {}
        if isinstance(req, dict):
            if not req.get("prompt") and not req.get("prompts"):
                errors.append(f"scenario {sid or i}: request.prompt or prompts required")
        else:
            errors.append(f"scenario {sid or i}: request must be a mapping")
        expected = sc.get("expected") or {}
        if expected and not isinstance(expected, dict):
            errors.append(f"scenario {sid or i}: expected must be a mapping")
        coverage = doc.get("coverage")
        if coverage is not None and not isinstance(coverage, dict):
            errors.append("coverage must be a mapping")
        mix = doc.get("mix")
        if mix is not None:
            if not isinstance(mix, dict):
                errors.append("mix must be a mapping of use_case -> weight")
            else:
                for k, v in mix.items():
                    try:
                        float(v)
                    except (TypeError, ValueError):
                        errors.append(f"mix[{k}] must be numeric")
    return errors


def assert_valid_pack(doc: dict[str, Any], *, pack_id: str | None = None) -> dict[str, Any]:
    errors = validate_pack(doc, pack_id=pack_id)
    if errors:
        raise ScenarioSchemaError("; ".join(errors))
    return doc
