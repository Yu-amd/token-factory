"""Compile UI metadata JSON."""

from __future__ import annotations

from typing import Any

from token_factory.version import PINNED_VERSIONS, VIRTUAL_MODEL


def _routing_matrix_metadata(policy: dict[str, Any]) -> dict[str, Any]:
    """Light V2 pointers for UI/CLI — does not change the V1 gateway path."""
    priority_mode = policy.get("priority_mode", "balanced")
    policy_name = policy.get("name")
    objective = priority_mode
    policy_version = None
    policy_catalog = "policies/amd-policy.yaml"
    try:
        from token_factory.routing_matrix.loader import load_routing_bundle

        bundle = load_routing_bundle()
        aliases = bundle["use_cases"].get("priority_mode_aliases") or {}
        # Prefer explicit profile name (amd-balanced) then priority_mode
        objective = aliases.get(policy_name or "", aliases.get(priority_mode, priority_mode))
        policy_version = (
            (bundle["policy"].get("metadata") or {})
            .get("amd_routing_policy", {})
            .get("version")
            or bundle["policy"].get("version")
        )
        policy_catalog = (
            (bundle["policy"].get("metadata") or {})
            .get("amd_routing_policy", {})
            .get("canonical_path")
            or bundle["policy"].get("_source_path")
            or policy_catalog
        )
    except Exception:
        # Compile must not fail if additive catalogs are absent
        fallback = {
            "balanced": "balanced",
            "cost": "token-cost",
            "quality": "quality",
            "latency": "latency",
            "edge": "edge-local",
            "enterprise": "enterprise",
            "amd-balanced": "balanced",
            "amd-quality": "quality",
            "amd-cost-efficient": "token-cost",
            "amd-low-latency": "latency",
            "amd-edge-first": "edge-local",
            "amd-enterprise": "enterprise",
        }
        objective = fallback.get(policy_name or "", fallback.get(priority_mode, priority_mode))

    return {
        "available": True,
        "doc": "docs/amd-routing-matrix.md",
        "policy_doc": "docs/policy-model.md",
        "cli": "token-factory recommend",
        "policy_cli": "token-factory policy",
        "policy_catalog": policy_catalog,
        "policy_version": policy_version,
        "priority_mode": priority_mode,
        "policy_name": policy_name,
        "objective_alias": objective,
        "thesis": {
            "aim_support": "CAN RUN",
            "amd_recommendation": "SHOULD RUN",
            "runtime_inventory": "AVAILABLE NOW",
            "compiled_routes": "ACTIVE EXECUTION",
        },
    }


def compile_ui_metadata(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
    token_factory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policies.get("policy", {})
    endpoint_map = {ep["id"]: ep for ep in endpoints.get("endpoints", []) if ep.get("enabled", True)}
    routes = []
    for route in policy.get("routes", []):
        ep = endpoint_map.get(route.get("endpoint_ref", ""))
        if not ep:
            continue
        routes.append(
            {
                "name": route.get("name"),
                "lora_name": route.get("lora_name") or route.get("name"),
                "domains": route.get("domains", []),
                "endpoint": {
                    "id": ep["id"],
                    "host": ep["host"],
                    "port": ep["port"],
                    "model": ep["model"],
                    "role": ep.get("role"),
                    "hardware": ep.get("hardware"),
                    "accelerator": ep.get("accelerator"),
                },
            }
        )

    out: dict[str, Any] = {
        "virtual_model": policy.get("virtual_model")
        or (token_factory or {}).get("virtual_model", VIRTUAL_MODEL),
        "policy_name": policy.get("name"),
        "priority_mode": policy.get("priority_mode", "balanced"),
        "routes": routes,
        "endpoints": endpoints.get("endpoints", []),
        "routing_matrix": _routing_matrix_metadata(policy),
        "links": {
            "gateway": "http://127.0.0.1:18080",
            "semantic_router_api": "http://127.0.0.1:8081",
            "semantic_router_dashboard": "http://localhost:8700",
            "grafana": "http://127.0.0.1:3000",
            "prometheus": "http://127.0.0.1:9090",
        },
        "pinned_versions": PINNED_VERSIONS,
    }

    # Rich Policies tab payload from canonical AMD policy (additive; compile stays resilient)
    try:
        from token_factory.policy.compile import policy_ui_metadata

        out["amd_policy"] = policy_ui_metadata(
            profile_name=policy.get("name"),
            endpoints=endpoints,
            v1_policies=policies,
        )
    except Exception as exc:
        out["amd_policy"] = {
            "available": False,
            "error": f"{exc.__class__.__name__}: {exc}",
            "version": out["routing_matrix"].get("policy_version"),
        }

    return out
