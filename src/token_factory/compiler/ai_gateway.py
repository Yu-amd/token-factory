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
    # Use fqdn for DNS names, ip for literal addresses.
    endpoint: dict[str, Any]
    parts = host.split(".")
    is_ipv4 = len(parts) == 4 and all(p.isdigit() for p in parts)
    if is_ipv4:
        endpoint = {"ip": {"address": host, "port": port}}
    else:
        endpoint = {"fqdn": {"hostname": host, "port": port}}
    return {
        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
        "kind": "Backend",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {"endpoints": [endpoint]},
    }


def _gateway_traffic_policy(gateway_name: str, namespace: str) -> dict[str, Any]:
    # WHY: BackendTrafficPolicy may only target Gateway/HTTPRoute/... (not Backend).
    # Health checks + retries apply at the gateway scope for demo reliability.
    return {
        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
        "kind": "BackendTrafficPolicy",
        "metadata": {"name": "token-factory-failover", "namespace": namespace},
        "spec": {
            "targetRefs": [
                {
                    "group": "gateway.networking.k8s.io",
                    "kind": "Gateway",
                    "name": gateway_name,
                }
            ],
            "healthCheck": {
                "active": {
                    "type": "HTTP",
                    "http": {"path": "/v1/models", "expectedStatuses": [200]},
                    "interval": "10s",
                    "timeout": "3s",
                    "unhealthyThreshold": 2,
                    "healthyThreshold": 1,
                }
            },
            "retry": {
                "numRetries": 2,
                "retryOn": {
                    "triggers": [
                        "connect-failure",
                        "refused-stream",
                        "unavailable",
                        "reset",
                    ]
                },
            },
        },
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

    # EnvoyProxy with ClusterIP — kind/local clusters often lack LoadBalancer.
    # WHY: Gateway stays Programmed=False without an address on kind.
    # UPSTREAM: Envoy Gateway EnvoyProxy provider.kubernetes.envoyService.type
    # WHEN IT CAN BE REMOVED: when deploying with MetalLB/cloud LB by default.
    manifests.append(
        {
            "apiVersion": "gateway.envoyproxy.io/v1alpha1",
            "kind": "EnvoyProxy",
            "metadata": {"name": "token-factory-proxy", "namespace": gateway_ns},
            "spec": {
                "provider": {
                    "type": "Kubernetes",
                    "kubernetes": {"envoyService": {"type": "ClusterIP"}},
                }
            },
        }
    )
    manifests.append(
        {
            "apiVersion": "gateway.networking.k8s.io/v1",
            "kind": "GatewayClass",
            "metadata": {"name": "envoy"},
            "spec": {
                "controllerName": "gateway.envoyproxy.io/gatewayclass-controller",
                "parametersRef": {
                    "group": "gateway.envoyproxy.io",
                    "kind": "EnvoyProxy",
                    "name": "token-factory-proxy",
                    "namespace": gateway_ns,
                },
            },
        }
    )

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
    fallback_chain = (
        policies.get("policy", {}).get("fallback", {}).get("chain", [])
        if policies.get("policy", {}).get("fallback", {}).get("enabled", True)
        else []
    )

    emitted_backends: set[str] = set()
    for ep in endpoint_map.values():
        backend_name = f"backend-{ep['id']}"
        if backend_name in emitted_backends:
            continue
        emitted_backends.add(backend_name)
        manifests.append(_backend_manifest(backend_name, ep["host"], ep["port"], gateway_ns))
        manifests.append(_aiservice_backend(backend_name, gateway_ns))

    manifests.append(_gateway_traffic_policy(gateway_name, gateway_ns))

    # Merge routes that share the same x-ai-eg-model match key.
    rules_by_model: dict[str, dict[str, Any]] = {}
    for route in routes:
        ep = endpoint_map.get(route["endpoint_ref"])
        if not ep:
            continue
        route_model = route.get("lora_name") or ep["model"]
        primary_name = f"backend-{ep['id']}"
        backend_refs = [
            {
                "name": primary_name,
                "modelNameOverride": ep["model"],
                "priority": 0,
            }
        ]
        # Same-model endpoint failover only. Cross-model fallback requires body
        # rewrite (modelNameOverride), which is unreliable under dual extproc.
        priority = 1
        for fb_id in fallback_chain:
            if fb_id == route["endpoint_ref"]:
                continue
            fb_ep = endpoint_map.get(fb_id)
            if not fb_ep or fb_ep["model"] != ep["model"]:
                continue
            backend_refs.append(
                {
                    "name": f"backend-{fb_id}",
                    "modelNameOverride": fb_ep["model"],
                    "priority": priority,
                }
            )
            priority += 1

        if route_model not in rules_by_model:
            rules_by_model[route_model] = {
                "matches": [
                    {
                        "headers": [
                            {
                                "type": "Exact",
                                "name": "x-ai-eg-model",
                                "value": route_model,
                            },
                        ]
                    }
                ],
                "backendRefs": backend_refs,
                "timeouts": {"request": "120s", "backendRequest": "120s"},
            }

    aigw_rules = list(rules_by_model.values())

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
