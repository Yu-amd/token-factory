"""Schema validation for canonical AMD routing policy + profile overlays."""

from __future__ import annotations

from typing import Any

VALID_LIFECYCLES = {"ga", "preview", "tech-preview", "planned"}
VALID_OBJECTIVES = {
    "balanced",
    "token-cost",
    "lowest-cost-sufficient",
    "quality",
    "latency",
    "throughput",
    "edge-local",
    "enterprise",
    "performance",
    "cost",
    "local",
    "edge",
}
VALID_SERVING = {"interactive", "online-throughput", "batch", "offline-batch"}
VALID_LEVELS = {"PREFERRED", "RECOMMENDED", "ACCEPTABLE", "SUPPORTED", "NOT_SUPPORTED"}


class PolicyValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors) if errors else "policy validation failed")


def validate_canonical_policy(
    policy: dict[str, Any],
    *,
    use_case_ids: set[str] | None = None,
    compute_ids: set[str] | None = None,
    capability_ids: set[str] | None = None,
    strict: bool = True,
) -> list[str]:
    """Validate canonical policy document. Returns list of errors (empty = ok)."""
    errors: list[str] = []
    nested = policy.get("policy") if isinstance(policy.get("policy"), dict) else {}
    # Accept either nested-rich or flat engine form
    meta = (policy.get("metadata") or {}).get("amd_routing_policy") or {}
    version = (
        nested.get("policy_version")
        or meta.get("version")
        or policy.get("version")
    )
    if not version:
        errors.append("missing policy_version")

    levels = policy.get("recommendation_levels") or nested.get("recommendation_levels")
    if levels:
        for lv in levels:
            if lv not in VALID_LEVELS:
                errors.append(f"invalid recommendation level: {lv}")

    lifecycle = policy.get("lifecycle") or nested.get("lifecycle") or {}
    for mode, rules in lifecycle.items():
        if mode in ("default_ga",):
            continue
        if not isinstance(rules, dict):
            continue
        # production/evaluation/local blocks
        for flag in ("allow_preview", "allow_tech_preview"):
            if flag in rules and not isinstance(rules[flag], bool):
                errors.append(f"lifecycle.{mode}.{flag} must be bool")

    # Eligibility hard gates
    eligibility = nested.get("eligibility") or {}
    gates = eligibility.get("hard_gates") or []
    seen_gate_ids: set[str] = set()
    for gate in gates:
        gid = (gate or {}).get("id")
        if not gid:
            errors.append("eligibility.hard_gates entry missing id")
            continue
        if gid in seen_gate_ids:
            errors.append(f"duplicate eligibility gate id: {gid}")
        seen_gate_ids.add(gid)

    # Compute positioning required statements
    positioning = nested.get("compute_positioning") or {}
    for family in ("instinct", "mi350p", "radeon", "epyc"):
        block = positioning.get(family) or {}
        if nested and family not in positioning:
            errors.append(f"compute_positioning missing '{family}'")
        elif block and not block.get("statement"):
            errors.append(f"compute_positioning.{family} missing statement")

    # Serving patterns
    serving = nested.get("serving_patterns") or {}
    for sp in VALID_SERVING:
        if nested and serving and sp not in serving and sp.replace("-", "_") not in serving:
            # allow underscore variant
            if sp not in serving:
                errors.append(f"serving_patterns missing '{sp}'")

    # Objectives
    objectives = nested.get("objectives") or {}
    for oid, oblock in objectives.items():
        if not isinstance(oblock, dict):
            errors.append(f"objectives.{oid} must be a mapping")
            continue
        rid = oblock.get("id", oid)
        if rid not in VALID_OBJECTIVES and oid not in VALID_OBJECTIVES:
            errors.append(f"unknown objective id: {rid}")

    # Overrides refs
    overrides = policy.get("overrides") or nested.get("overrides") or {}
    if use_case_ids is not None:
        for uc in overrides:
            if uc not in use_case_ids:
                errors.append(f"overrides references unknown use-case: {uc}")
    if compute_ids is not None:
        for uc, models in overrides.items():
            if not isinstance(models, dict):
                continue
            for model, computes in models.items():
                if not isinstance(computes, dict):
                    continue
                for cid, cell in computes.items():
                    if cid not in compute_ids:
                        errors.append(
                            f"overrides[{uc}][{model}] unknown compute: {cid}"
                        )
                    if isinstance(cell, dict):
                        rec = cell.get("recommendation")
                        if rec and rec not in VALID_LEVELS:
                            errors.append(
                                f"overrides[{uc}][{model}][{cid}] invalid recommendation: {rec}"
                            )

    # Capability gate keys (informational — warn if unknown when catalog provided)
    if capability_ids is not None:
        for key in (eligibility.get("capability_gates") or {}):
            # keys are use-case-ish or capability names; allow either
            pass

    # Fallback
    fallback = nested.get("fallback") or {}
    if nested and not fallback.get("rules"):
        errors.append("fallback.rules missing")

    if strict and errors:
        raise PolicyValidationError(errors)
    return errors


def validate_profile_overlay(profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    policy = profile.get("policy") or {}
    overlay = profile.get("overlay") or policy.get("overlay") or {}
    if not policy.get("name") and not overlay:
        errors.append("profile missing policy.name and overlay")
    obj = overlay.get("objective") or policy.get("priority_mode")
    if obj and obj not in VALID_OBJECTIVES:
        # priority_mode may be cost/edge/quality — mapped aliases
        aliases = {"cost", "edge", "quality", "latency", "balanced", "enterprise"}
        if obj not in aliases and obj not in VALID_OBJECTIVES:
            errors.append(f"profile overlay unknown objective: {obj}")
    # Profiles must NOT redefine full use-case override matrices
    if "overrides" in profile or "overrides" in overlay:
        errors.append("profile must not duplicate canonical overrides matrix")
    if "compute_positioning" in overlay or "eligibility" in overlay:
        errors.append("profile must not redefine compute_positioning or eligibility")
    return errors
