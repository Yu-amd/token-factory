"""Compile UI metadata JSON."""

from __future__ import annotations

from typing import Any

from token_factory.version import PINNED_VERSIONS, VIRTUAL_MODEL


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

    return {
        "virtual_model": policy.get("virtual_model")
        or (token_factory or {}).get("virtual_model", VIRTUAL_MODEL),
        "policy_name": policy.get("name"),
        "priority_mode": policy.get("priority_mode", "balanced"),
        "routes": routes,
        "endpoints": endpoints.get("endpoints", []),
        "links": {
            "gateway": "http://localhost:8080",
            "semantic_router_api": "http://localhost:8081",
            "semantic_router_dashboard": "http://localhost:8700",
            "grafana": "http://localhost:3000",
            "prometheus": "http://localhost:9090",
        },
        "pinned_versions": PINNED_VERSIONS,
    }
