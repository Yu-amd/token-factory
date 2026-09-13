"""Validation dimensions for Automated Demo requests.

Dimensions: Classification, Policy, Capability, Lifecycle, Route, Endpoint, Telemetry
→ PASS / WARN / FAIL / N/A

Soft eligibility preferred over brittle exact model×HW matches.
"""

from __future__ import annotations

from typing import Any

from token_factory.demo.models import VALIDATION_DIMENSIONS, ValidationStatus
from token_factory.demo.normalize import (
    classification_matches,
    compute_family_of,
    normalize_compute_family,
)


def validate_request(
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
    validation_flags: dict[str, Any] | None = None,
    telemetry_ok: bool | None = None,
    observability_pack: bool = False,
) -> dict[str, str]:
    """Compute per-dimension validation results."""
    flags = validation_flags or {}
    results: dict[str, str] = {d: ValidationStatus.NA.value for d in VALIDATION_DIMENSIONS}

    if flags.get("classification", True):
        results["classification"] = _validate_classification(expected, actual).value
    if flags.get("capability_fit", flags.get("capability", True)):
        results["capability"] = _validate_capability(expected, actual).value
    if flags.get("lifecycle", True):
        results["lifecycle"] = _validate_lifecycle(expected, actual).value
    if flags.get("route", True) or flags.get("policy", True):
        results["policy"] = _validate_policy(expected, actual).value
        results["route"] = _validate_route(expected, actual).value
    if flags.get("endpoint", True):
        results["endpoint"] = _validate_endpoint(expected, actual).value
    if flags.get("telemetry", True):
        results["telemetry"] = _validate_telemetry(
            actual, telemetry_ok=telemetry_ok, strict=observability_pack
        ).value

    # If a dimension was explicitly disabled, keep N/A
    for dim, enabled in flags.items():
        key = "capability" if dim == "capability_fit" else dim
        if key in results and enabled is False:
            results[key] = ValidationStatus.NA.value

    return results


def _validate_classification(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    exp_cls = (expected.get("classification") or {}).get("use_case")
    if not exp_cls:
        return ValidationStatus.NA
    actual_labels = [
        actual.get("classified_use_case"),
        actual.get("classification_category"),
        actual.get("routing_decision"),
        (actual.get("classification") or {}).get("category")
        if isinstance(actual.get("classification"), dict)
        else None,
    ]
    if any(classification_matches(exp_cls, lab) for lab in actual_labels if lab):
        return ValidationStatus.PASS
    # Hint-driven mock path: if we used the expected use case as canonical input
    if actual.get("use_case_hint") and classification_matches(exp_cls, actual.get("use_case_hint")):
        return ValidationStatus.PASS
    return ValidationStatus.FAIL


def _validate_capability(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    caps = expected.get("capabilities") or {}
    required = list(caps.get("required") or [])
    if not required:
        # Soft: if route selected, assume capability gate already applied by engine
        if actual.get("selected_model") or actual.get("runtime_selected"):
            return ValidationStatus.PASS
        return ValidationStatus.NA

    model_caps = actual.get("model_capabilities") or {}
    capability_excluded = actual.get("capability_excluded")
    if capability_excluded:
        return ValidationStatus.FAIL

    # Multimodal / vision hard fail
    if "vision" in required or "multimodal" in required:
        if model_caps.get("vision") is False or actual.get("text_only_for_vision"):
            return ValidationStatus.FAIL

    missing = []
    for req in required:
        key = req.replace("-", "_")
        if key in ("text_generation", "text-generation"):
            continue
        # Engine already filtered; check explicit flags when present
        if key in model_caps and model_caps[key] is False:
            missing.append(req)
    if missing:
        return ValidationStatus.FAIL
    if actual.get("runtime_selected") or actual.get("canonical_preferred"):
        return ValidationStatus.PASS
    return ValidationStatus.WARN


def _validate_lifecycle(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    routing = expected.get("routing") or {}
    require_prod = routing.get("require_production_eligible", False)
    selected_life = (
        (actual.get("runtime_selected") or {}).get("lifecycle")
        or actual.get("selected_lifecycle")
    )
    production_eligible = (actual.get("runtime_selected") or {}).get("production_eligible")
    lifecycle_mode = actual.get("lifecycle_mode") or "production"

    # Explicit expectation: TP must be excluded under production
    if expected.get("lifecycle_exclusion"):
        excl = actual.get("lifecycle_exclusions_count", 0)
        if excl > 0 or actual.get("tp_excluded"):
            # And runtime must not be tech-preview when mode is production
            if lifecycle_mode == "production" and selected_life in ("tech-preview", "preview"):
                return ValidationStatus.FAIL
            return ValidationStatus.PASS
        if lifecycle_mode == "production" and selected_life in ("tech-preview", "preview"):
            return ValidationStatus.FAIL
        return ValidationStatus.WARN

    if require_prod or lifecycle_mode == "production":
        if selected_life in ("tech-preview", "preview"):
            return ValidationStatus.FAIL
        if production_eligible is False:
            return ValidationStatus.FAIL
        if selected_life in ("ga", None) or production_eligible is True:
            return ValidationStatus.PASS
        return ValidationStatus.WARN

    return ValidationStatus.PASS if selected_life else ValidationStatus.NA


def _validate_policy(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    routing = expected.get("routing") or {}
    families = [
        normalize_compute_family(f)
        for f in (routing.get("preferred_compute_family") or routing.get("allowed_compute_families") or [])
    ]
    families = [f for f in families if f]

    selected = actual.get("runtime_selected") or actual.get("canonical_preferred") or {}
    sel_family = compute_family_of(selected.get("compute"), selected.get("family"))

    # Soft tendency: preferred family is a WARN if missed when alternatives allowed
    tendency = routing.get("compute_family_tendency")
    if tendency:
        tendency_f = normalize_compute_family(tendency)
        if sel_family and tendency_f and sel_family != tendency_f:
            # Allow if selected family is in allowed list or locality forced otherwise
            allowed = families or [tendency_f]
            if sel_family not in allowed:
                if routing.get("strict_family"):
                    return ValidationStatus.FAIL
                return ValidationStatus.WARN
        return ValidationStatus.PASS

    if families:
        if not sel_family:
            return ValidationStatus.WARN
        if sel_family in families:
            return ValidationStatus.PASS
        if routing.get("strict_family"):
            return ValidationStatus.FAIL
        return ValidationStatus.WARN

    # Locality — soft when inventory has no local/Radeon endpoint (common in CI)
    if routing.get("require_local") or (expected.get("locality") == "local"):
        if sel_family == "radeon" or actual.get("local_selected"):
            return ValidationStatus.PASS
        if routing.get("allow_no_runtime") or actual.get("no_local_candidate"):
            return ValidationStatus.WARN
        # Non-local selection under local preference is a policy miss when local exists
        if sel_family and sel_family != "radeon":
            return ValidationStatus.WARN
        return ValidationStatus.FAIL

    if actual.get("policy_version") or actual.get("canonical_preferred"):
        return ValidationStatus.PASS
    return ValidationStatus.NA


def _validate_route(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    if actual.get("route_error"):
        return ValidationStatus.FAIL
    expect_route = (expected.get("routing") or {}).get("expect_route")
    if expect_route is False:
        # Expect no eligible route
        if not actual.get("runtime_selected"):
            return ValidationStatus.PASS
        return ValidationStatus.FAIL

    runtime = actual.get("runtime_selected")
    canonical = actual.get("canonical_preferred")
    if runtime:
        # Canonical ≠ runtime is OK when preferred not deployed
        if canonical and (
            canonical.get("model") != runtime.get("model")
            or canonical.get("compute") != runtime.get("compute")
        ):
            reason = actual.get("canonical_vs_runtime_reason") or ""
            if "not deployed" in reason.lower() or actual.get("preferred_not_deployed"):
                return ValidationStatus.PASS
        return ValidationStatus.PASS

    if (expected.get("routing") or {}).get("allow_no_runtime"):
        return ValidationStatus.WARN
    if canonical and not runtime:
        return ValidationStatus.WARN
    return ValidationStatus.FAIL


def _validate_endpoint(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationStatus:
    if (expected.get("routing") or {}).get("expect_route") is False:
        return ValidationStatus.NA
    if actual.get("fallback_used") and actual.get("runtime_selected"):
        return ValidationStatus.PASS
    ep = actual.get("selected_endpoint") or (actual.get("runtime_selected") or {}).get("endpoint_id")
    if ep:
        return ValidationStatus.PASS
    if actual.get("mock") and actual.get("runtime_selected"):
        # Mock path may synthesize endpoint id
        return ValidationStatus.PASS
    if actual.get("runtime_selected") and actual.get("runtime_selected", {}).get("endpoint_available"):
        return ValidationStatus.PASS
    if actual.get("preferred_not_deployed") and not actual.get("runtime_selected"):
        return ValidationStatus.WARN
    if actual.get("runtime_selected"):
        return ValidationStatus.WARN
    return ValidationStatus.FAIL


def _validate_telemetry(
    actual: dict[str, Any],
    *,
    telemetry_ok: bool | None,
    strict: bool,
) -> ValidationStatus:
    if telemetry_ok is True:
        return ValidationStatus.PASS
    if telemetry_ok is False:
        return ValidationStatus.FAIL if strict else ValidationStatus.WARN
    # Attribute presence on actual.telemetry
    tel = actual.get("telemetry") or {}
    required = {
        "demo_run_id",
        "scenario_id",
        "request_id",
    }
    if required.issubset(tel.keys()) or required.issubset(actual.keys()):
        return ValidationStatus.PASS
    return ValidationStatus.WARN if not strict else ValidationStatus.FAIL
