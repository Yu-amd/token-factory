# Architecture

Token Factory implements AMD Enterprise AI **Mixture-of-Models** routing on Kubernetes.

## Control plane vs data plane

| Layer | Component | Namespace |
|-------|-----------|-----------|
| Ingress | Envoy Gateway + AI Gateway | `envoy-gateway-system`, `envoy-ai-gateway-system` |
| Routing | vLLM Semantic Router v0.3 | `vllm-semantic-router-system` |
| Config | Token Factory compiler + CLI | repo / `token-factory` |
| Observability | Prometheus + Grafana | `observability` |

## Single source of truth

```
config/endpoints.yaml + policies/*.yaml + catalog/aims.yaml
        │
        ▼
  token-factory compile
        │
        ├── generated/semantic-router-values.yaml
        ├── generated/ai-gateway-manifests.yaml
        └── generated/ui-metadata.json
```

Clients call one virtual model: **`token-factory/auto`**.

## Request flow

1. Client POST `/v1/chat/completions` with `model: token-factory/auto`
2. Envoy AI Gateway applies auth, rate limits, extproc hook
3. Semantic Router classifies domain → sets `x-ai-eg-model` (LoRA route)
4. AIGatewayRoute maps header → AIServiceBackend → OpenAI-compatible endpoint
5. Metrics exported to Prometheus; dashboards in Grafana and SR dashboard (:8700)

See [routing-policy.md](routing-policy.md) and [eai-sr-demo-parity.md](eai-sr-demo-parity.md).
