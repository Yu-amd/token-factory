"""Compile Envoy AI Gateway manifests (v0.3.0 CRDs)."""

from __future__ import annotations

from typing import Any


def _backend_manifest(name: str, host: str, port: int, namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
        "kind": "Backend",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"endpoints": [{"ip": {"address": host, "port": port}}]},
    }


def _aiservice_backend(name: str, namespace: str) -> dict[str, Any]:
    return {
        "apiVersion": "aigateway.envoyproxy.io/v1alpha1",
        "kind": "AIServiceBackend",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "schema": {"name": "OpenAI"},
            "backendRef": {
                "name": name,
                "kind": "Backend",
                "group": "gateway.envoyproxy.io",
            },
        },
    }


def compile_ai_gateway_manifests(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
    token_factory: dict[str, Any],
) -> list[dict[str, Any]]:
    cluster = token_factory.get("cluster", {})
    gateway_name = cluster.get("gateway_name", "semantic-router")
    gateway_ns = cluster.get("gateway_namespace", "token-factory")
    manifests: list[dict[str, Any]] = []

    manifests.append(
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "Gateway",
            "metadata": {"name": gateway_name, "namespace": gateway_ns},
            "spec": {
                "gatewayClassName": "envoy",
                "listeners": [{"name": "http", "protocol": "HTTP", "port": 80}],
            },
        }
    )

    endpoint_map = {ep["id"]: ep for ep in endpoints.get("endpoints", []) if ep.get("enabled", True)}
    routes = policies.get("policy", {}).get("routes", [])
    backend_names: dict[str, str] = {}

    for route in routes:
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        backend_name = route.get("backend_name") or f"backend-{route['endpoint_ref']}"
        backend_names[route.get("lora_name") or route["name"]] = backend_name
        manifests.append(_backend_manifest(backend_name, ep["host"], ep["port"], gateway_ns))
        manifests.append(_aiservice_backend(backend_name, gateway_ns))

    aigw_rules = []
    for route in routes:
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        lora = route.get("lora_name") or route["name"]
        backend_name = route.get("backend_name") or f"backend-{route['endpoint_ref']}"
        aigw_rules.append(
            {
                "matches": [
                    {
                        "headers": [
                            {
                                "type": "Exact",
                                "name": "x-ai-eg-model",
                                "value": lora,
                            }
                        ]
                    }
                ],
                "backendRefs": [
                    {"name": backend_name, "modelNameOverride": ep["model"]},
                ],
                "timeouts": {"request": "120s", "backendRequest": "120s"},
            }
        )

    manifests.append(
        {
            "apiVersion": "aigateway.envoyproxy.io/v1alpha1",
            "kind": "AIGatewayRoute",
            "metadata": {"name": gateway_name, "namespace": gateway_ns},
            "spec": {
                "parentRefs": [
                    {
                        "name": gateway_name,
                        "kind": "Gateway",
                        "group": "gateway.networking.k8s.io",
                    }
                ],
                "rules": aigw_rules,
            },
        }
    )

    manifests.append(
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "EnvoyPatchPolicy",
            "metadata": {"name": "semantic-router-extproc", "namespace": gateway_ns},
            "spec": {
                "targetRef": {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": gateway_name,
                },
                "type": "JSONPatch",
                "jsonPatches": [
                    {
                        "name": f"{gateway_ns}/{gateway_name}/http",
                        "type": "type.googleapis.com/envoy.config.listener.v3.Listener",
                        "operation": {
                            "op": "add",
                            "path": "/default_filter_chain/filters/0/typed_config/http_filters/0",
                            "value": {
                                "name": "semantic-router-extproc",
                                "typedConfig": {
                                    "@type": (
                                        "type.googleapis.com/envoy.extensions.filters.http"
                                        ".ext_proc.v3.ExternalProcessor"
                                    ),
                                    "grpcService": {
                                        "envoyGrpc": {
                                            "authority": "semantic-router.vllm-semantic-router-system:50051",
                                            "clusterName": "semantic-router",
                                        },
                                        "timeout": "60s",
                                    },
                                    "processing_mode": {
                                        "request_body_mode": "BUFFERED",
                                        "request_header_mode": "SEND",
                                    },
                                },
                            },
                        },
                    }
                ],
            },
        }
    )

    return manifests
