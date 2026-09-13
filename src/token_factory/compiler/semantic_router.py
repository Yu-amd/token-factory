"""Compile Semantic Router Helm values from endpoints + policies."""

from __future__ import annotations

from typing import Any

from token_factory.version import PINNED_VERSIONS, VIRTUAL_MODEL


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/v1"


def _model_cards(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for route in routes:
        model_name = route.get("model_card") or route.get("endpoint_ref", "base-model")
        lora = route.get("lora_name") or route.get("name", "general-expert")
        card = cards.setdefault(
            model_name,
            {"name": model_name, "description": route.get("description", ""), "loras": []},
        )
        card["loras"].append({"name": lora, "description": route.get("description", "")})
    return list(cards.values())


def compile_semantic_router_values(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
    token_factory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policies.get("policy", {})
    endpoint_map = {ep["id"]: ep for ep in endpoints.get("endpoints", []) if ep.get("enabled", True)}
    routes = policy.get("routes", [])

    provider_models: list[dict[str, Any]] = []
    seen_cards: set[str] = set()
    for route in routes:
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        card_name = route.get("model_card") or f"{ep['role']}-model"
        if card_name not in seen_cards:
            seen_cards.add(card_name)
            provider_models.append(
                {
                    "name": card_name,
                    "backend_refs": [
                        {
                            "name": ep["model"],
                            "provider": "openai",
                            "base_url": _base_url(ep["host"], ep["port"]),
                            "weight": ep.get("weight", 1),
                        }
                    ],
                }
            )

    decisions = []
    for route in sorted(routes, key=lambda r: r.get("priority", 0), reverse=True):
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        card_name = route.get("model_card") or f"{ep['role']}-model"
        decisions.append(
            {
                "name": route["name"],
                "description": route.get("description", ""),
                "priority": route.get("priority", 1),
                "rules": {
                    "operator": "OR",
                    "conditions": [{"type": "domain", "name": d} for d in route["domains"]],
                },
                "modelRefs": [
                    {
                        "model": card_name,
                        "lora_name": route.get("lora_name") or route["name"],
                        "use_reasoning": route.get("use_reasoning", False),
                    }
                ],
            }
        )

    signals = policy.get("signals", {})
    domains = signals.get("domains") or [
        {"name": d, "description": d.replace("_", " ")}
        for route in routes
        for d in route.get("domains", [])
    ]
    # dedupe domains
    seen_domains: set[str] = set()
    unique_domains = []
    for domain in domains:
        name = domain["name"] if isinstance(domain, dict) else domain
        if name not in seen_domains:
            seen_domains.add(name)
            if isinstance(domain, dict):
                unique_domains.append(domain)
            else:
                unique_domains.append({"name": domain, "description": domain})

    sr_config = {
        "version": "v0.3",
        "listeners": [],
        "providers": {
            "defaults": {"default_model": provider_models[0]["name"] if provider_models else "base-model"},
            "models": provider_models,
        },
        "routing": {
            "modelCards": _model_cards(
                [
                    {
                        **route,
                        "model_card": route.get("model_card")
                        or f"{endpoint_map[route['endpoint_ref']]['role']}-model",
                    }
                    for route in routes
                    if route["endpoint_ref"] in endpoint_map
                ]
            ),
            "decisions": decisions,
            "signals": {"domains": unique_domains},
        },
        "global": {},
    }

    dashboard_cfg = (token_factory or {}).get("components", {}).get(
        "semantic_router", {}
    ).get("dashboard", {})

    return {
        "env": [
            {
                "name": "HF_TOKEN",
                "valueFrom": {
                    "secretKeyRef": {"name": "hf-token-secret", "key": "token"},
                },
            }
        ],
        "config": sr_config,
        "dashboard": {
            "enabled": dashboard_cfg.get("enabled", True),
            "replicaCount": 1,
            "image": {
                "repository": "ghcr.io/vllm-project/semantic-router/dashboard",
                "tag": PINNED_VERSIONS["semantic_router_app"],
                "pullPolicy": "IfNotPresent",
            },
            "service": {"type": "ClusterIP", "port": 8700, "targetPort": 8700},
        },
        "dependencies": {"semanticCache": {"redis": {"enabled": False}}},
        "replicaCount": 1,
        "metadata": {
            "virtual_model": policy.get("virtual_model")
            or (token_factory or {}).get("virtual_model", VIRTUAL_MODEL),
        },
    }
