"""Executive-facing presentation of demo validation outcomes.

Internal ValidationStatus remains PASS / WARN / FAIL / N/A.
Soft, policy-aware WARN conditions are presented as ADVISORY.
Telemetry / unexpected gaps stay WARN. FAIL is never downgraded.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from token_factory.demo.models import ValidationStatus
from token_factory.demo.normalize import compute_family_of, normalize_compute_family


class PresentationStatus(str, Enum):
    PASS = "PASS"
    ADVISORY = "ADVISORY"
    WARN = "WARN"
    FAIL = "FAIL"
    NA = "N/A"


# Normalized advisory-reason taxonomy (presentation only).
ADVISORY_REASONS = (
    "preferred_compute_unavailable",
    "runtime_inventory_constraint",
    "local_candidate_unavailable",
    "lifecycle_evaluation",
    "soft_family_tendency_mismatch",
    "allowed_no_runtime",
    "observability_warning",
    "other_warning",
)

_REASON_MESSAGES = {
    "preferred_compute_unavailable": (
        "Preferred compute family unavailable in current runtime inventory"
    ),
    "runtime_inventory_constraint": (
        "Canonical preferred model×compute not deployed; eligible alternate used"
    ),
    "local_candidate_unavailable": (
        "No eligible local runtime target is currently deployed"
    ),
    "lifecycle_evaluation": "Evaluation / preview lifecycle route is intentional",
    "soft_family_tendency_mismatch": (
        "Preferred compute tendency not satisfied by current runtime constraints"
    ),
    "allowed_no_runtime": "Scenario allows no runtime when inventory cannot satisfy preference",
    "observability_warning": "Unexpected non-fatal observability / telemetry condition",
    "other_warning": "Non-fatal condition requiring attention",
}


@dataclass(frozen=True)
class PresentationResult:
    status: str
    advisory_reason: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "advisory_reason": self.advisory_reason,
            "message": self.message,
        }


def overall_validation_status(validation: dict[str, str] | None) -> ValidationStatus:
    """Mirror DemoRequest.overall() without requiring a DemoRequest instance."""
    statuses = [ValidationStatus.coerce(v) for v in (validation or {}).values()]
    if any(s == ValidationStatus.FAIL for s in statuses):
        return ValidationStatus.FAIL
    if any(s == ValidationStatus.WARN for s in statuses):
        return ValidationStatus.WARN
    if statuses and all(s in (ValidationStatus.PASS, ValidationStatus.NA) for s in statuses):
        if any(s == ValidationStatus.PASS for s in statuses):
            return ValidationStatus.PASS
    return ValidationStatus.NA


def classify_presentation_status(
    validation: dict[str, str],
    actual: dict[str, Any] | None,
    expected: dict[str, Any] | None,
) -> PresentationResult:
    """Map internal validation → executive presentation status.

    Rules:
    - FAIL stays FAIL
    - PASS stays PASS (including PASS + runtime_escalation)
    - Telemetry / unexpected WARNs stay WARN
    - Soft inventory / locality / tendency / evaluation WARNs → ADVISORY
    - Do not blindly map every WARN → ADVISORY
    - Do not auto-classify runtime_escalation as advisory
    """
    actual = actual or {}
    expected = expected or {}
    overall = overall_validation_status(validation)

    if overall == ValidationStatus.FAIL:
        return PresentationResult(
            status=PresentationStatus.FAIL.value,
            message="Routing/policy correctness violation",
        )
    if overall == ValidationStatus.PASS:
        return PresentationResult(
            status=PresentationStatus.PASS.value,
            message="Expected policy behavior",
        )
    if overall == ValidationStatus.NA:
        return PresentationResult(status=PresentationStatus.NA.value)

    # overall == WARN
    warn_dims = {
        dim
        for dim, val in (validation or {}).items()
        if ValidationStatus.coerce(val) == ValidationStatus.WARN
    }
    soft_dims = warn_dims - {"telemetry"}
    has_telemetry_warn = "telemetry" in warn_dims

    # Unexpected observability issues always surface as WARN (even alongside soft WARNs).
    if has_telemetry_warn and not soft_dims:
        return PresentationResult(
            status=PresentationStatus.WARN.value,
            advisory_reason="observability_warning",
            message=_REASON_MESSAGES["observability_warning"],
        )
    if has_telemetry_warn and soft_dims:
        # Soft + telemetry: keep WARN so unexpected issues are not hidden.
        return PresentationResult(
            status=PresentationStatus.WARN.value,
            advisory_reason="observability_warning",
            message=_REASON_MESSAGES["observability_warning"],
        )

    reason = _classify_advisory_reason(warn_dims, actual, expected)
    if reason is None:
        return PresentationResult(
            status=PresentationStatus.WARN.value,
            advisory_reason="other_warning",
            message=_REASON_MESSAGES["other_warning"],
        )

    return PresentationResult(
        status=PresentationStatus.ADVISORY.value,
        advisory_reason=reason,
        message=_REASON_MESSAGES.get(reason),
    )


def _classify_advisory_reason(
    warn_dims: set[str],
    actual: dict[str, Any],
    expected: dict[str, Any],
) -> str | None:
    """Return an advisory reason when WARN dims are explained by soft structured fields."""
    routing = expected.get("routing") or {}
    allow_no_runtime = bool(routing.get("allow_no_runtime"))
    require_local = bool(routing.get("require_local")) or expected.get("locality") == "local"
    tendency = routing.get("compute_family_tendency")
    preferred_families = [
        normalize_compute_family(f)
        for f in (
            routing.get("preferred_compute_family")
            or routing.get("allowed_compute_families")
            or []
        )
    ]
    preferred_families = [f for f in preferred_families if f]

    selected = actual.get("runtime_selected") or actual.get("canonical_preferred") or {}
    sel_family = compute_family_of(
        actual.get("selected_compute") or selected.get("compute"),
        actual.get("selected_compute_family") or selected.get("family"),
    )
    no_local = bool(actual.get("no_local_candidate"))
    preferred_not_deployed = bool(actual.get("preferred_not_deployed"))
    lifecycle_mode = str(actual.get("lifecycle_mode") or "").lower()
    selected_life = str(
        actual.get("selected_lifecycle")
        or (actual.get("runtime_selected") or {}).get("lifecycle")
        or ""
    ).lower()

    # Local / private soft miss (most specific).
    if "policy" in warn_dims and require_local and (no_local or allow_no_runtime):
        if no_local or (sel_family and sel_family != "radeon"):
            return "local_candidate_unavailable"

    # Soft compute-family tendency miss.
    if tendency and "policy" in warn_dims:
        tendency_f = normalize_compute_family(tendency)
        if sel_family and tendency_f and sel_family != tendency_f:
            return "soft_family_tendency_mismatch"

    # Preferred family unavailable (soft preference, not strict).
    if preferred_families and "policy" in warn_dims:
        if not sel_family or sel_family not in preferred_families:
            if not routing.get("strict_family"):
                return "preferred_compute_unavailable"

    # Explicit allow-no-runtime with route/endpoint soft miss.
    if allow_no_runtime and warn_dims & {"route", "endpoint", "policy"}:
        if not actual.get("runtime_selected") or preferred_not_deployed or no_local:
            return "allowed_no_runtime"

    # Evaluation / preview intentional soft surface.
    if "lifecycle" in warn_dims or lifecycle_mode in ("evaluation", "all"):
        if lifecycle_mode in ("evaluation", "all") or selected_life in (
            "tech-preview",
            "preview",
            "evaluation",
        ):
            return "lifecycle_evaluation"

    # Preferred model×compute not in inventory (route/endpoint soft WARN).
    if preferred_not_deployed and warn_dims & {"route", "endpoint", "policy", "capability"}:
        return "runtime_inventory_constraint"

    # Capability soft WARN without hard exclusion — inventory/evaluation gap.
    if warn_dims <= {"capability", "endpoint", "route", "policy", "lifecycle"}:
        if preferred_not_deployed or allow_no_runtime or require_local or tendency:
            # Structured soft signals present but order above did not fire — inventory bucket.
            if preferred_not_deployed:
                return "runtime_inventory_constraint"
            if allow_no_runtime:
                return "allowed_no_runtime"
            if tendency:
                return "soft_family_tendency_mismatch"
            if require_local:
                return "local_candidate_unavailable"

    return None
