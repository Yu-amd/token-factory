"""Explain Policy — seven-step reasoning from the canonical engine."""

from __future__ import annotations

from typing import Any

from token_factory.config.loader import load_endpoints
from token_factory.policy.loader import apply_profile_overlay, load_canonical_policy
from token_factory.routing_matrix.engine import RecommendationEngine
from token_factory.routing_matrix.loader import load_routing_bundle


def explain_policy(
    use_case: str,
    *,
    objective: str | None = None,
    serving_pattern: str | None = None,
    traffic: str = "medium",
    lifecycle: str = "production",
    deployment: str | None = None,
    data_locality: bool = False,
    latency_requirement: str | None = None,
    profile: str | None = None,
    endpoints: list[dict[str, Any]] | None = None,
    engine: RecommendationEngine | None = None,
) -> dict[str, Any]:
    """Return structured Explain Policy steps (1–7) for UI/CLI.

    Uses the same RecommendationEngine path as the Routing Matrix — no parallel logic.
    """
    if engine is None:
        bundle = load_routing_bundle()
        if profile:
            bundle = dict(bundle)
            bundle["policy"] = apply_profile_overlay(bundle["policy"], profile)
        engine = RecommendationEngine(bundle)

    if endpoints is None:
        endpoints = load_endpoints().get("endpoints", [])

    if use_case not in engine.use_cases:
        raise KeyError(f"unknown use case: {use_case}")

    uc = engine.use_cases[use_case]
    objective = engine.resolve_objective(objective, use_case)
    serving_pattern = engine.resolve_serving_pattern(serving_pattern, use_case)
    latency_requirement = engine.resolve_latency_requirement(
        use_case, serving_pattern, latency_requirement
    )
    lifecycle_mode = engine.resolve_lifecycle_mode(lifecycle)

    sim = engine.simulate_route(
        use_case,
        objective=objective,
        utilization=traffic,
        endpoints=endpoints,
        lifecycle_mode=lifecycle_mode,
        data_locality=data_locality,
        serving_pattern=serving_pattern,
        latency_requirement=latency_requirement,
    )
    rec = engine.recommend(
        use_case,
        objective=objective,
        utilization=traffic,
        endpoints=endpoints,
        lifecycle_mode=lifecycle_mode,
        data_locality=data_locality,
        serving_pattern=serving_pattern,
        latency_requirement=latency_requirement,
        deployment=deployment,
        show="all",
    )
    rec.pop("_pool", None)

    canonical = load_canonical_policy()
    nested = canonical.get("_canonical") or canonical.get("policy") or {}
    positioning = (nested.get("compute_positioning") or {}) if isinstance(nested, dict) else {}

    caps_req = (uc.get("capabilities") or {}).get("required") or []
    caps_pref = (uc.get("capabilities") or {}).get("preferred") or []
    floor = engine.capability_floors.get(use_case, "standard")

    # Step 3 — compute policy notes from positioning + serving pattern
    compute_notes: list[str] = []
    if serving_pattern in ("batch", "offline-batch"):
        compute_notes.append(
            (positioning.get("epyc") or {}).get("statement")
            or "EPYC may rise for batch / offline with relaxed latency."
        )
    if serving_pattern == "interactive" and traffic == "high":
        compute_notes.append(
            "EPYC receives lower serving-pattern fit for interactive + high traffic."
        )
        compute_notes.append(
            (positioning.get("instinct") or {}).get("statement")
            or "Instinct preferred for high-concurrency interactive."
        )
    if data_locality or objective == "edge-local":
        compute_notes.append(
            (positioning.get("radeon") or {}).get("statement")
            or "Radeon preferred when locality matters and capability clears."
        )
    if lifecycle_mode == "evaluation":
        compute_notes.append(
            (positioning.get("mi350p") or {}).get("statement")
            or "MI350P Tech Preview eligible under evaluation lifecycle."
        )

    ranked = rec.get("ranked") or []
    preferred = ranked[:5]
    selected = sim.get("selected_runtime_route")
    fallback_chain = []
    profile_meta = (engine.policy.get("_profile") or {}) if isinstance(engine.policy, dict) else {}
    if profile_meta.get("fallback"):
        fallback_chain = (profile_meta["fallback"] or {}).get("chain") or []
    elif nested.get("fallback"):
        fallback_chain = []

    steps = [
        {
            "step": 1,
            "title": "Capability Requirements",
            "required": caps_req,
            "preferred": caps_pref,
            "capability_floor": floor,
            "use_case": {
                "id": use_case,
                "display_name": uc.get("display_name", use_case),
                "category": uc.get("category"),
            },
        },
        {
            "step": 2,
            "title": "Eligibility Rules Applied",
            "hard_gates": (nested.get("eligibility") or {}).get("hard_gates") or [],
            "lifecycle_mode": lifecycle_mode,
            "allowed_lifecycles": sorted(sim.get("allowed_lifecycles") or []),
            "lifecycle_exclusions": len(sim.get("lifecycle_exclusions") or []),
            "notes": [
                g.get("rule")
                for g in ((nested.get("eligibility") or {}).get("hard_gates") or [])
                if isinstance(g, dict)
            ],
        },
        {
            "step": 3,
            "title": "Compute Policy",
            "serving_pattern": serving_pattern,
            "latency_requirement": latency_requirement,
            "traffic": traffic,
            "data_locality": data_locality,
            "notes": compute_notes,
            "positioning_label": (positioning.get("continuum_label")),
        },
        {
            "step": 4,
            "title": "Ranking Objective",
            "objective": objective,
            "objective_meta": (nested.get("objectives") or {}).get(objective)
            or (nested.get("objectives") or {}).get(
                {
                    "token-cost": "lowest-cost-sufficient",
                    "quality": "quality",
                }.get(objective, objective)
            ),
            "preference_label": rec.get("preference_label"),
        },
        {
            "step": 5,
            "title": "Preferred Candidates",
            "candidates": preferred,
            "counts": rec.get("counts"),
        },
        {
            "step": 6,
            "title": "Runtime Availability",
            "selected_runtime_route": selected,
            "currently_deployed_eligible": sim.get("currently_deployed_eligible") or [],
            "explanation": sim.get("explanation"),
        },
        {
            "step": 7,
            "title": "Fallback",
            "canonical_rules": (nested.get("fallback") or {}).get("rules") or [],
            "profile_fallback_chain": fallback_chain,
            "serving_pattern_notes": sim.get("serving_pattern_exclusions") or [],
            "locality_notes": sim.get("locality_exclusions") or [],
        },
    ]

    return {
        "use_case": sim["use_case"],
        "objective": objective,
        "serving_pattern": serving_pattern,
        "latency_requirement": latency_requirement,
        "traffic": traffic,
        "lifecycle_mode": lifecycle_mode,
        "deployment": deployment,
        "data_locality": data_locality,
        "policy_version": rec.get("policy_version") or sim.get("policy_version"),
        "steps": steps,
        "amd_recommendation": preferred,
        "selected_runtime_route": selected,
        "explanation": sim.get("explanation"),
        "matrix_consistent": True,
    }
