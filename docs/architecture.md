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
2. Envoy AI Gateway applies **extproc** to vLLM-SR (auth/rate-limit CRs are **not** compiled today)
3. Semantic Router classifies domain → sets `x-ai-eg-model` (LoRA / model route)
4. AIGatewayRoute maps header → AIServiceBackend → OpenAI-compatible endpoint
5. Metrics exported to Prometheus; dashboards in Grafana and SR dashboard (:8700)

## Phase 1 — Two-Tier vLLM-SR AI Gateway Blueprint

**Governs where model requests run.**

The slide’s **Tier 1 (Provider Gateway)** and **Tier 2 (Inference Gateway)** are
**logical labels** over a single Envoy AI Gateway + vLLM-SR path — not separate
runtimes. Token Factory emits honest decision objects so the demo never paints
unwired features as live. Full audit: [phase1-architecture-gap.md](phase1-architecture-gap.md).

```text
Client / application
        │
        ▼
Ingress / AI Gateway (Envoy AI Gateway)          ← live OSS (pluggable)
        │
        ▼
Logical Tier 1 — Provider / model decision       ← vLLM-SR classify + AMD policy
   ├─ provider/model selection                   ← LIVE
   ├─ upstream/provider auth                     ← NOT ENABLED (no SecurityPolicy)
   ├─ token/rate controls                        ← NOT ENABLED
   ├─ same-model endpoint failover               ← CONFIGURED when spare shares model
   └─ cross-model fallback                       ← NOT PROVEN
        │
        ▼
Logical Tier 2 — Inference placement             ← compile-time route → endpoint
   ├─ endpoint / compute selection               ← LIVE (static map + health probe)
   ├─ load-aware routing                         ← NOT ENABLED
   ├─ KV-cache awareness                         ← NOT ENABLED
   ├─ prefix-cache awareness                     ← NOT ENABLED
   └─ P/D disaggregation                         ← NOT ENABLED
        │
        ▼
execution targets
   ├─ MI300X / AMD Instinct hosted models        ← live AIM / OpenAI-compatible
   └─ optional frontier / SaaS model endpoints   ← pluggable later
```

Playground Phase 1 live flow:

`CLIENT → AI GATEWAY → vLLM-SR → AMD POLICY → MODEL / MI300X`

Verify honesty before an executive demo:

```bash
token-factory verify phase1 --live
```

## Phase 2 — Agent Gateway + Semantic Routing Blueprint

**Governs the broader agent execution graph.** vLLM-SR remains on the **model** branch only.
MCP servers and sub-agents are **peer** execution targets of Agent Gateway — never under vLLM-SR.

```text
Client / agent
        │
        ▼
Agent Gateway                                         ← mock/demo (Friday) · agentgateway later
   ├─ AuthN / AuthZ
   ├─ quotas / rate limits
   ├─ policy enforcement
   ├─ tracing / observability
   ├─ MCP / A2A governance
   └─ provider auth
        │
        ├── MODEL REQUEST ──► vLLM Semantic Router
        │                         ├─ intent / classification
        │                         ├─ capability / economics
        │                         ├─ AMD lifecycle / policy
        │                         └─ endpoint selection → MI300X / frontier
        │
        ├── MCP REQUEST ──► MCP servers               ← peer (not under vLLM-SR)
        │
        └── A2A REQUEST ──► sub-agents                ← peer (not under vLLM-SR)
```

| Component | Friday status | Notes |
|-----------|---------------|--------|
| Envoy AI Gateway | live OSS | replaceable via `GatewayAdapter` |
| vLLM Semantic Router | live OSS | replaceable via `ModelRouterAdapter` |
| Agent Gateway | **mock/demo** | same interface → agentgateway / commercial later |
| MI300X AIM endpoints | live | env-configured `execution_targets` / `endpoints.yaml` |
| MCP / A2A peers | mock/open demo | peer adapters; not under SR |
| Prometheus + Grafana | live OSS | Phase 1 + Phase 2 counters |

See [svp-demo-plan.md](svp-demo-plan.md) for adapter contracts, SVP script, and P0/P1/P2.

### Streaming caveat

OpenAI `stream: true` through Envoy AI Gateway v0.4.0 typically **buffers the full
SSE body** (TTFT ≈ full generation). The Playground avoids that by classifying via
the Semantic Router API (`/api/v1/classify/intent`) and streaming **directly from the
selected AIM endpoint** for live TTFT. Set `TF_PLAYGROUND_DIRECT_STREAM=0` to force
the gateway path. Gateway streaming remains a V2 fix when AIGW ModeOverride works
with dual SR extproc.

See [routing-policy.md](routing-policy.md) and [eai-sr-demo-parity.md](eai-sr-demo-parity.md).
