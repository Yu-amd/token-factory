"""Compile Envoy AI Gateway manifests (AIGW v0.4.0 — AIServiceBackend/AIGatewayRoute)."""

from __future__ import annotations

from typing import Any

SR_NAMESPACE = "vllm-semantic-router-system"
SR_GRPC_HOST = f"semantic-router.{SR_NAMESPACE}.svc.cluster.local"
EXT_PROC_TYPE = (
    "type.googleapis.com/envoy.extensions.filters.http.ext_proc.v3.ExternalProcessor"
)
CLUSTER_TYPE = "type.googleapis.com/envoy.config.cluster.v3.Cluster"
LISTENER_TYPE = "type.googleapis.com/envoy.config.listener.v3.Listener"


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


def _extproc_patch(gateway_ns: str, gateway_name: str) -> dict[str, Any]:
    return {
        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
        "kind": "EnvoyPatchPolicy",
        "metadata": {"name": "ai-gateway-prepost-extproc-patch-policy", "namespace": gateway_ns},
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
                    "type": LISTENER_TYPE,
                    "operation": {
                        "op": "add",
                        "path": "/default_filter_chain/filters/0/typed_config/http_filters/0",
                        "value": {
                            "name": "semantic-router-extproc",
                            "typedConfig": {
                                "@type": EXT_PROC_TYPE,
                                "allow_mode_override": True,
                                "grpcService": {
                                    "envoyGrpc": {
                                        "authority": f"semantic-router.{SR_NAMESPACE}:50051",
                                        "clusterName": "semantic-router",
                                    },
                                    "timeout": "60s",
                                },
                                "message_timeout": "60s",
                                "processing_mode": {
                                    "request_body_mode": "BUFFERED",
                                    "request_header_mode": "SEND",
                                    "request_trailer_mode": "SKIP",
                                    "response_body_mode": "NONE",
                                    "response_header_mode": "SEND",
                                    "response_trailer_mode": "SKIP",
                                },
                            },
                        },
                    },
                },
                {
                    "name": "semantic-router",
                    "type": CLUSTER_TYPE,
                    "operation": {
                        "op": "add",
                        "path": "",
                        "value": {
                            "name": "semantic-router",
                            "type": "STRICT_DNS",
                            "connect_timeout": "60s",
                            "http2_protocol_options": {},
                            "lb_policy": "ROUND_ROBIN",
                            "load_assignment": {
                                "cluster_name": "semantic-router",
                                "endpoints": [
                                    {
                                        "lb_endpoints": [
                                            {
                                                "endpoint": {
                                                    "address": {
                                                        "socket_address": {
                                                            "address": SR_GRPC_HOST,
                                                            "port_value": 50051,
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                ],
                            },
                        },
                    },
                },
            ],
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

    endpoint_map = {
        ep["id"]: ep for ep in endpoints.get("endpoints", []) if ep.get("enabled", True)
    }
    routes = policies.get("policy", {}).get("routes", [])

    for route in routes:
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        backend_name = route.get("backend_name") or f"backend-{route['endpoint_ref']}"
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
                            {"type": "Exact", "name": "x-ai-eg-model", "value": lora},
                        ]
                    }
                ],
                "backendRefs": [{"name": backend_name, "modelNameOverride": ep["model"]}],
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
                    {"name": gateway_name, "kind": "Gateway", "group": "gateway.networking.k8s.io"},
                ],
                "rules": aigw_rules,
            },
        }
    )

    manifests.append(_extproc_patch(gateway_ns, gateway_name))

    manifests.append(
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "ClientTrafficPolicy",
            "metadata": {"name": "large-buffer", "namespace": gateway_ns},
            "spec": {
                "targetRefs": [
                    {"group": "gateway.networking.k8s.io", "kind": "Gateway", "name": gateway_name},
                ],
                "connection": {"bufferLimit": "32Mi"},
            },
        }
    )

    manifests.append(
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "HTTPRoute",
            "metadata": {"name": "token-factory-health", "namespace": gateway_ns},
            "spec": {
                "parentRefs": [{"name": gateway_name}],
                "rules": [
                    {
                        "matches": [{"path": {"type": "PathPrefix", "value": "/health"}}],
                        "backendRefs": [
                            {
                                "name": "semantic-router",
                                "namespace": SR_NAMESPACE,
                                "port": 8080,
                                "kind": "Service",
                                "group": "",
                            }
                        ],
                    }
                ],
            },
        }
    )

    manifests.append(
        {
            "apiVersion": "gateway.networking.k8s.io/v1beta1",
            "kind": "ReferenceGrant",
            "metadata": {"name": "allow-token-factory-to-sr", "namespace": SR_NAMESPACE},
            "spec": {
                "from": [
                    {
                        "group": "gateway.networking.k8s.io",
                        "kind": "HTTPRoute",
                        "namespace": gateway_ns,
                    }
                ],
                "to": [{"group": "", "kind": "Service"}],
            },
        }
    )

    return manifests
