"""Endpoint eligibility against AIM catalog."""

from __future__ import annotations

from typing import Any

from token_factory.catalog.loader import find_aim, support_level_for

SUPPORT_RANK = {
    "optimized": 4,
    "preview": 3,
    "unoptimized": 2,
    "general": 1,
}


def endpoint_eligibility(
    endpoint: dict[str, Any],
    catalog: dict[str, Any],
    min_support: str = "general",
) -> dict[str, Any]:
    model = endpoint.get("model", "")
    hardware = endpoint.get("hardware", "instinct")
    accelerator = endpoint.get("accelerator", "")
    aim = find_aim(catalog, model)
    if not aim:
        return {
            "eligible": False,
            "reason": f"model '{model}' not found in AIM catalog",
            "support_level": None,
        }

    family_map = {"instinct": "instinct", "epyc": "epyc", "radeon": "radeon"}
    family = family_map.get(hardware, "instinct")
    if not accelerator:
        accelerators = catalog.get("accelerators", {}).get(family, [])
        accelerator = accelerators[0] if accelerators else ""

    level = support_level_for(aim, family, accelerator)
    if level is None:
        return {
            "eligible": False,
            "reason": f"no support entry for {family}/{accelerator}",
            "support_level": None,
        }

    eligible = SUPPORT_RANK.get(level, 0) >= SUPPORT_RANK.get(min_support, 1)
    return {
        "eligible": eligible,
        "reason": "ok" if eligible else f"support level '{level}' below minimum '{min_support}'",
        "support_level": level,
        "accelerator": accelerator,
        "family": family,
    }


def select_fallback_endpoint(
    endpoints: list[dict[str, Any]],
    catalog: dict[str, Any],
    chain: list[str],
    min_support: str = "general",
) -> dict[str, Any] | None:
    by_id = {ep["id"]: ep for ep in endpoints if ep.get("enabled", True)}
    for endpoint_id in chain:
        ep = by_id.get(endpoint_id)
        if not ep:
            continue
        result = endpoint_eligibility(ep, catalog, min_support=min_support)
        if result["eligible"]:
            return ep
    return None
