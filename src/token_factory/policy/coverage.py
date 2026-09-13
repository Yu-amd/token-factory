"""Policy coverage — every use case has a path or an explicit gap."""

from __future__ import annotations

from typing import Any

from token_factory.routing_matrix.engine import RecommendationEngine
from token_factory.routing_matrix.loader import load_routing_bundle


def policy_coverage(
    *,
    engine: RecommendationEngine | None = None,
    lifecycle_modes: list[str] | None = None,
    objectives: list[str] | None = None,
) -> dict[str, Any]:
    """Compute coverage stats from the live engine (no fabricated counts)."""
    engine = engine or RecommendationEngine(load_routing_bundle())
    lifecycle_modes = lifecycle_modes or ["production", "production-preview", "evaluation"]
    # Default probe: use-case default objective + balanced
    use_cases = list(engine.use_cases.values())
    rows: list[dict[str, Any]] = []
    ga_capable = 0
    preview_only = 0
    tp_only = 0
    no_candidate = 0
    gaps: list[dict[str, Any]] = []

    for uc in use_cases:
        uc_id = uc["id"]
        objective = uc.get("optimization_default", "balanced")
        serving = (uc.get("serving_patterns_preferred") or ["interactive"])[0]
        row: dict[str, Any] = {
            "use_case": uc_id,
            "display_name": uc.get("display_name", uc_id),
            "category": uc.get("category"),
            "objective_default": objective,
            "serving_pattern_default": serving,
            "required_capabilities": (uc.get("capabilities") or {}).get("required") or [],
            "paths": {},
            "gap": None,
        }
        prod = engine.recommend(
            uc_id,
            objective=objective,
            lifecycle_mode="production",
            serving_pattern=serving,
            show="recommended+supported",
            limit=5,
        )
        prev = engine.recommend(
            uc_id,
            objective=objective,
            lifecycle_mode="production-preview",
            serving_pattern=serving,
            show="recommended+supported",
            limit=5,
        )
        ev = engine.recommend(
            uc_id,
            objective=objective,
            lifecycle_mode="evaluation",
            serving_pattern=serving,
            show="recommended+supported",
            limit=5,
        )
        for label, result in (
            ("production", prod),
            ("production-preview", prev),
            ("evaluation", ev),
        ):
            top = (result.get("ranked") or result.get("candidates") or [])[:3]
            row["paths"][label] = [
                {"model": c["model"], "compute": c["compute"], "recommendation": c["recommendation"]}
                for c in top
            ]

        if prod["counts"]["ranked"] > 0:
            ga_capable += 1
            status = "ga-capable"
        elif prev["counts"]["ranked"] > 0:
            preview_only += 1
            status = "preview-only"
            row["gap"] = "No GA path — Preview AIM required"
        elif ev["counts"]["ranked"] > 0:
            tp_only += 1
            status = "tech-preview-only"
            row["gap"] = "No GA/Preview path — Tech Preview only (e.g. MI350P)"
        else:
            no_candidate += 1
            status = "no-eligible-candidate"
            row["gap"] = "No eligible candidate under any lifecycle mode"
            gaps.append(
                {
                    "use_case": uc_id,
                    "reason": row["gap"],
                    "required": row["required_capabilities"],
                }
            )
        row["status"] = status
        # Family hints from evaluation top
        families = {
            c["family"]
            for c in (ev.get("ranked") or [])[:8]
            if c.get("family")
        }
        row["compute_families"] = sorted(families)
        rows.append(row)

    nested = (engine.policy.get("_canonical") or engine.policy.get("policy") or {})
    if not isinstance(nested, dict):
        nested = {}
    policy_meta = (engine.policy.get("metadata") or {}).get("amd_routing_policy") or {}

    return {
        "policy_version": policy_meta.get("version") or engine.policy.get("version"),
        "published": policy_meta.get("published"),
        "counts": {
            "use_cases": len(use_cases),
            "objectives": len(engine.list_objectives()),
            "serving_patterns": len(engine.list_serving_patterns()),
            "compute_targets": len(engine.list_compute()),
            "lifecycle_modes": len(engine.list_lifecycle_modes()),
            "ga_capable": ga_capable,
            "preview_only": preview_only,
            "tech_preview_only": tp_only,
            "no_eligible_candidate": no_candidate,
        },
        "use_cases": rows,
        "gaps": gaps,
        "eligibility_gates": (nested.get("eligibility") or {}).get("hard_gates") or [],
        "compute_positioning": nested.get("compute_positioning") or {},
    }
