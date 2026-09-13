"""Config validation."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from token_factory.config.schema import (
    AIM_CATALOG_SCHEMA,
    ENDPOINTS_SCHEMA,
    POLICIES_SCHEMA,
    TOKEN_FACTORY_SCHEMA,
)


class ConfigValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _validate(schema: dict[str, Any], data: dict[str, Any], label: str) -> list[str]:
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{label}: {path}: {err.message}")
    return errors


def validate_endpoints(data: dict[str, Any]) -> list[str]:
    return _validate(ENDPOINTS_SCHEMA, data, "endpoints")


def validate_policies(data: dict[str, Any]) -> list[str]:
    return _validate(POLICIES_SCHEMA, data, "policies")


def validate_token_factory(data: dict[str, Any]) -> list[str]:
    return _validate(TOKEN_FACTORY_SCHEMA, data, "token-factory")


def validate_aim_catalog(data: dict[str, Any]) -> list[str]:
    return _validate(AIM_CATALOG_SCHEMA, data, "aim-catalog")


def validate_cross_references(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    endpoint_ids = {ep["id"] for ep in endpoints.get("endpoints", []) if ep.get("enabled", True)}
    for route in policies.get("policy", {}).get("routes", []):
        ref = route.get("endpoint_ref")
        if ref and ref not in endpoint_ids:
            errors.append(f"policies: route '{route.get('name')}' references unknown endpoint '{ref}'")
    fallback = policies.get("policy", {}).get("fallback", {})
    if fallback.get("enabled", True):
        for ref in fallback.get("chain", []):
            if ref not in endpoint_ids:
                errors.append(f"policies: fallback chain references unknown endpoint '{ref}'")
    return errors


def validate_all(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
    token_factory: dict[str, Any] | None = None,
    catalog: dict[str, Any] | None = None,
) -> None:
    errors: list[str] = []
    errors.extend(validate_endpoints(endpoints))
    errors.extend(validate_policies(policies))
    if token_factory:
        errors.extend(validate_token_factory(token_factory))
    if catalog:
        errors.extend(validate_aim_catalog(catalog))
    errors.extend(validate_cross_references(endpoints, policies))
    if errors:
        raise ConfigValidationError(errors)
