"""Failure-injection overlays for demo runtime only — never mutate canonical policy."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from token_factory.demo.normalize import compute_family_of, normalize_compute_family

# Injection tokens accepted by CLI / UI
INJECTION_ALIASES = {
    "preferred-endpoint-unavailable": "preferred-endpoint-unavailable",
    "preferred_endpoint_unavailable": "preferred-endpoint-unavailable",
    "no-radeon": "no-radeon",
    "no_radeon": "no-radeon",
    "no-epyc": "no-epyc",
    "no_epyc": "no-epyc",
    "no-local": "no-local",
    "no_local": "no-local",
    "no-instinct": "no-instinct",
    "no_instinct": "no-instinct",
    "lifecycle-restriction": "lifecycle-restriction",
    "lifecycle_restriction": "lifecycle-restriction",
}


def normalize_injections(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        key = INJECTION_ALIASES.get(str(item).strip().lower().replace(" ", "-"), None)
        if key and key not in out:
            out.append(key)
    return out


def apply_endpoint_overlay(
    endpoints: list[dict[str, Any]],
    injections: list[str],
    *,
    preferred_endpoint_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return a filtered/disabled copy of endpoint inventory for this demo run.

    Does not mutate the caller's list or any on-disk config.
    """
    inj = set(normalize_injections(injections))
    overlay = deepcopy(endpoints)
    result: list[dict[str, Any]] = []
    for ep in overlay:
        hw = (ep.get("hardware") or ep.get("family") or "").lower()
        accel = (ep.get("accelerator") or ep.get("compute") or "").upper()
        family = compute_family_of(accel, hw) or normalize_compute_family(hw)
        tags = {str(t).lower() for t in (ep.get("tags") or [])}
        locality = "local" in tags or family == "radeon" or (ep.get("deployment") in ("local", "workstation", "edge"))

        if "no-radeon" in inj and family == "radeon":
            continue
        if "no-epyc" in inj and family == "epyc":
            continue
        if "no-instinct" in inj and family == "instinct":
            continue
        if "no-local" in inj and locality:
            continue
        if "preferred-endpoint-unavailable" in inj:
            if preferred_endpoint_id and ep.get("id") == preferred_endpoint_id:
                ep = dict(ep)
                ep["enabled"] = False
                ep["_demo_injected_unavailable"] = True
                continue  # treat as unavailable
            # If no preferred id yet, mark first enabled endpoint unavailable later in runner
        if ep.get("enabled") is False and not ep.get("_demo_keep"):
            # preserve disabled mocks unless explicitly kept
            pass
        result.append(ep)
    return result


def mark_preferred_unavailable(
    endpoints: list[dict[str, Any]],
    preferred: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Remove the preferred model×compute endpoint from the overlay (fallback test)."""
    if not preferred:
        return endpoints
    pref_model = preferred.get("model")
    pref_compute = preferred.get("compute")
    pref_id = preferred.get("endpoint_id")
    out: list[dict[str, Any]] = []
    for ep in endpoints:
        if pref_id and ep.get("id") == pref_id:
            continue
        if pref_model and ep.get("model") == pref_model:
            accel = (ep.get("accelerator") or "").upper()
            if not pref_compute or accel == str(pref_compute).upper():
                continue
        out.append(ep)
    return out


def effective_lifecycle(lifecycle_mode: str, injections: list[str]) -> str:
    """Force production lifecycle when lifecycle-restriction injection is active."""
    inj = set(normalize_injections(injections))
    if "lifecycle-restriction" in inj:
        return "production"
    return lifecycle_mode
