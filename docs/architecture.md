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
config/endpoints.yaml + policies/amd-policy.yaml + policies/profiles/*.yaml + catalog/aims.yaml
        │
        ▼
  token-factory compile  (+ token-factory policy compile)
        │
        ├── generated/semantic-router-values.yaml
        ├── generated/ai-gateway-manifests.yaml
        └── generated/ui-metadata.json  (includes amd_policy for Policies tab)
```

Clients call one virtual model: **`token-factory/auto`**.

## AMD Opinionated Routing (additive)

```text
AIM CATALOG          = CAN RUN
AMD CANONICAL POLICY = SHOULD RUN   (policies/amd-policy.yaml)
RUNTIME INVENTORY    = AVAILABLE NOW
COMPILED ROUTES      = ACTIVE EXECUTION
```

Profiles under `policies/profiles/` are **overlays** (objective / lifecycle / V1 SR routes),
not independent recommendation systems. See [policy-model.md](policy-model.md) and
[amd-routing-matrix.md](amd-routing-matrix.md). Compile still emits V1 manifests plus
`routing_matrix` and `amd_policy` fields in `ui-metadata.json`.
### AMD Compute Positioning

- **EPYC** — CPU-centric / batch / low-QPS / fleet utilization — **not** a GPU interactive competitor; rises for batch/offline + relaxed latency; does not auto-rise for high-concurrency interactive.
- **Radeon** — local / workstation / privacy; can win when capable + locality preferred.
- **MI350P** — PCIe enterprise Instinct (Tech Preview); between workstation and rack.
- **Instinct rack** — high-throughput / high-concurrency interactive and online-throughput.
See [amd-routing-matrix.md](amd-routing-matrix.md).

## Request flow

1. Client POST `/v1/chat/completions` with `model: token-factory/auto`
2. Envoy AI Gateway applies auth, rate limits, extproc hook
3. Semantic Router classifies domain → sets `x-ai-eg-model` (LoRA route)
4. AIGatewayRoute maps header → AIServiceBackend → OpenAI-compatible endpoint
5. Metrics exported to Prometheus; dashboards in Grafana and SR dashboard (:8700)

### Streaming caveat

OpenAI `stream: true` through Envoy AI Gateway v0.4.0 typically **buffers the full
SSE body** (TTFT ≈ full generation). The Playground avoids that by classifying via
the Semantic Router API (`/api/v1/classify/intent`) and streaming **directly from the
selected AIM endpoint** for live TTFT. Set `TF_PLAYGROUND_DIRECT_STREAM=0` to force
the gateway path. Gateway streaming remains a V2 fix when AIGW ModeOverride works
with dual SR extproc.

See [routing-policy.md](routing-policy.md) and [eai-sr-demo-parity.md](eai-sr-demo-parity.md).
