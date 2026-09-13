"""Compile effective policy metadata for UI + ranked candidates + runtime routes."""

from __future__ import annotations

from typing import Any

from token_factory.config.loader import load_endpoints, load_policies
from token_factory.policy.coverage import policy_coverage
from token_factory.policy.loader import (
    apply_profile_overlay,
    list_profiles,
    load_canonical_policy,
    load_profile,
)
from token_factory.routing_matrix.engine import RecommendationEngine
from token_factory.routing_matrix.loader import load_routing_bundle


def policy_ui_metadata(
    *,
    profile_name: str | None = None,
    endpoints: dict[str, Any] | None = None,
    v1_policies: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured metadata for the Policies tab — derived from canonical policy."""
    canonical = load_canonical_policy()
    nested = canonical.get("_canonical") or canonical.get("policy") or {}
    if not isinstance(nested, dict):
        nested = {}

    v1_policies = v1_policies or load_policies()
    v1_policy = v1_policies.get("policy") or {}
    profile_name = profile_name or v1_policy.get("name") or "amd-balanced"

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        profile = {"policy": v1_policy, "overlay": v1_policy.get("overlay") or {}}

    effective = apply_profile_overlay(canonical, profile)
    overlay = (profile.get("overlay") or (profile.get("policy") or {}).get("overlay") or {})

    bundle = load_routing_bundle()
    engine = RecommendationEngine(bundle)
    endpoints = endpoints or load_endpoints()
    ep_list = endpoints.get("endpoints") or []

    coverage = policy_coverage(engine=engine)
    profiles = list_profiles()

    # Compiled runtime routes from V1 policy pack + inventory
    endpoint_map = {ep["id"]: ep for ep in ep_list if ep.get("enabled", True)}
    compiled_routes = []
    for route in v1_policy.get("routes") or []:
        ep = endpoint_map.get(route.get("endpoint_ref", ""))
        compiled_routes.append(
            {
                "name": route.get("name"),
                "domains": route.get("domains") or [],
                "endpoint_ref": route.get("endpoint_ref"),
                "lora_name": route.get("lora_name"),
                "endpoint_available": ep is not None,
                "endpoint": (
                    {
                        "id": ep["id"],
                        "model": ep.get("model"),
                        "hardware": ep.get("hardware"),
                        "accelerator": ep.get("accelerator"),
                        "host": ep.get("host"),
                        "port": ep.get("port"),
                    }
                    if ep
                    else None
                ),
                "explainable_by": "V1 Semantic Router domain route constrained by AIM inventory; "
                "Matrix/Explain Policy share the same canonical SHOULD RUN source.",
            }
        )

    policy_meta = (canonical.get("metadata") or {}).get("amd_routing_policy") or {}

    return {
        "id": nested.get("id") or "amd-routing-policy",
        "display_name": nested.get("display_name") or "AMD Opinionated Routing Policy",
        "version": policy_meta.get("version") or nested.get("policy_version") or "2.3",
        "published": policy_meta.get("published") or nested.get("published"),
        "description": nested.get("description"),
        "source_path": canonical.get("_source_path") or nested.get("source_path"),
        "active_profile": profile_name,
        "virtual_model": v1_policy.get("virtual_model") or "token-factory/auto",
        "inputs": nested.get("inputs") or [],
        "eligibility_rules": (nested.get("eligibility") or {}).get("hard_gates") or [],
        "eligibility": nested.get("eligibility") or {},
        "compute_positioning": nested.get("compute_positioning") or {},
        "objectives": nested.get("objectives") or {},
        "serving_patterns": nested.get("serving_patterns") or {},
        "fallback_policy": nested.get("fallback") or {},
        "ranking_dimensions": nested.get("ranking_dimensions") or [],
        "provenance": nested.get("provenance") or {},
        "overlay": overlay,
        "profiles": profiles,
        "profile_comparison": [
            {
                "profile": p["id"],
                **(p.get("overlay") or {}).get("comparison", {}),
                "objective": p.get("objective"),
                "lifecycle_bias": (p.get("overlay") or {}).get("lifecycle_strictness"),
                "economics": (p.get("overlay") or {}).get("economic_preference"),
                "locality": (p.get("overlay") or {}).get("locality_preference"),
            }
            for p in profiles
        ],
        "coverage": {
            "counts": coverage["counts"],
            "gaps": coverage["gaps"],
            "use_cases": coverage["use_cases"],
        },
        "counts": {
            "use_cases": coverage["counts"]["use_cases"],
            "compute_targets": coverage["counts"]["compute_targets"],
            "models": len(engine.models),
            "objectives": coverage["counts"]["objectives"],
            "lifecycle_modes": coverage["counts"]["lifecycle_modes"],
            "capability_gates": len(
                ((nested.get("eligibility") or {}).get("capability_gates") or {})
            ),
            "hard_gates": len((nested.get("eligibility") or {}).get("hard_gates") or []),
            "profiles": len(profiles),
            "compiled_routes": len(compiled_routes),
            "endpoints": len(ep_list),
        },
        "compiled_routes": compiled_routes,
        "canonical_vs_runtime": {
            "canonical": {
                "source": canonical.get("_source_path"),
                "version": policy_meta.get("version"),
                "role": "SHOULD RUN (opinionated ranking + gates)",
            },
            "runtime": {
                "active_profile": profile_name,
                "priority_mode": v1_policy.get("priority_mode"),
                "routes": len(v1_policy.get("routes") or []),
                "fallback_chain": (v1_policy.get("fallback") or {}).get("chain") or [],
                "role": "ACTIVE EXECUTION (Semantic Router domain routes + inventory)",
            },
            "inventory": {
                "endpoints": len(ep_list),
                "role": "AVAILABLE NOW",
            },
            "aim_catalog": {
                "source": "catalog/aims.yaml",
                "role": "CAN RUN",
            },
        },
        "decision_pipeline": [
            "Use Case",
            "Capabilities",
            "Eligibility",
            "AIM Candidates",
            "Compute Fit",
            "Objective Ranking",
            "Lifecycle",
            "Endpoint Availability",
            "Compiled / Selected Route",
        ],
        "scenarios": [
            {
                "id": "interactive-coding",
                "label": "Interactive Coding",
                "use_case": "coding-assistant",
                "objective": "balanced",
                "serving_pattern": "interactive",
                "traffic": "medium",
                "lifecycle": "production",
            },
            {
                "id": "enterprise-chat-hc",
                "label": "High-Concurrency Enterprise Chat",
                "use_case": "enterprise-chat",
                "objective": "enterprise",
                "serving_pattern": "interactive",
                "traffic": "high",
                "lifecycle": "production",
            },
            {
                "id": "batch-summarization",
                "label": "Batch Summarization",
                "use_case": "batch-summarization",
                "objective": "token-cost",
                "serving_pattern": "batch",
                "traffic": "medium",
                "lifecycle": "production",
            },
            {
                "id": "local-multimodal",
                "label": "Local Multimodal",
                "use_case": "vlm",
                "objective": "edge-local",
                "serving_pattern": "interactive",
                "traffic": "low",
                "lifecycle": "production-preview",
                "data_locality": True,
            },
            {
                "id": "mi350p-evaluation",
                "label": "MI350P Evaluation",
                "use_case": "enterprise-chat",
                "objective": "balanced",
                "serving_pattern": "online-throughput",
                "traffic": "medium",
                "lifecycle": "evaluation",
            },
        ],
        "effective_overlay": {
            "active_objective": effective.get("active_objective") or overlay.get("objective"),
            "active_lifecycle_mode": effective.get("active_lifecycle_mode")
            or overlay.get("lifecycle_strictness"),
            "locality_preference": effective.get("locality_preference")
            or overlay.get("locality_preference"),
        },
    }


def compile_effective_policy(
    *,
    profile_name: str | None = None,
    use_case: str | None = None,
    objective: str | None = None,
) -> dict[str, Any]:
    """Combine canonical + profile + AIM + use cases + compute + endpoints."""
    meta = policy_ui_metadata(profile_name=profile_name)
    bundle = load_routing_bundle()
    engine = RecommendationEngine(bundle)
    endpoints = load_endpoints().get("endpoints") or []
    ranked = None
    if use_case:
        obj = objective or meta.get("effective_overlay", {}).get("active_objective") or "balanced"
        ranked = engine.recommend(
            use_case,
            objective=obj,
            endpoints=endpoints,
            lifecycle_mode=meta.get("effective_overlay", {}).get("active_lifecycle_mode")
            or "production",
        )
        ranked.pop("_pool", None)
    return {
        "effective_policy": meta,
        "ranked_candidates": ranked,
        "compiled_runtime_routes": meta.get("compiled_routes"),
    }
