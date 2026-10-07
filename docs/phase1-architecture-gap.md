# Phase 1 architecture gap analysis

Audit against the slide **“Phase 1: Two-Tier vLLM-SR AI Gateway Blueprint.”**  
Rule: only mark a feature **implemented** if Token Factory configures it **and** the request path exercises it. Upstream vLLM-SR capability alone does not count.

## Intended blueprint

```text
Client
  → Ingress / AI Gateway
  → Tier 1 — Provider Gateway
       unified provider interface · upstream/provider auth · token/rate controls
       provider/model fallback · LLM observability
  → Tier 2 — Inference Gateway
       load-aware · KV-cache · prefix-cache · P/D disaggregation awareness
  → Self-hosted MI300X / MI355X
Tier 1 may also route to external/frontier providers.
```

## What actually runs today

```text
Client (model: token-factory/auto)
  → Envoy AI Gateway (:18080)          # extproc → SR gRPC; healthCheck + retry only
  → vLLM Semantic Router               # domain classify → x-ai-eg-model header
  → AIGatewayRoute match on header
  → AIServiceBackend → AIM OpenAI endpoint (MI300X)

Playground default (TTFT):
  → SR /api/v1/classify/intent
  → stream DIRECTLY to AIM (gateway bypassed for body stream)
```

**Tier 1 and Tier 2 are not distinct runtimes.** They are slide/logical labels overlaid on one classify→header→backend path. Token Factory now emits explicit **Tier1ProviderDecision** / **Tier2InferenceDecision** objects so the demo can show what is live vs `not enabled`.

## Capability audit

| # | Capability | Status | Evidence |
|---|------------|--------|----------|
| 1 | Distinct Tier 1 / Tier 2 stages | **Logical labels only** | No separate Provider Gateway vs Inference Gateway processes/CRs. See `phase1/decisions.py`. |
| 2 | vLLM-SR features in Helm | **PARTIAL** | Domain decisions, providers.models, `auto_model_name`. `dependencies.semanticCache.redis.enabled: false`. No load/KV/prefix/PD keys. |
| 3 | Load-aware routing | **NOT ENABLED** | Static `weight: 1` on backend_refs; no load signals used for selection. |
| 4 | KV-cache-aware routing | **NOT ENABLED** | No config keys; not on request path. |
| 5 | Prefix-cache-aware routing | **NOT ENABLED** | Semantic-cache Redis off; not prefix-cache routing. |
| 6 | P/D disaggregation | **NOT ENABLED** | No config; not on request path. |
| 7 | Provider / model fallback | **PARTIAL / NOT PROVEN** | Compiler supports **same-model** `priority` backendRefs only. Cross-model chain in policy does not emit secondary refs. E2E failover not proven. |
| 8 | Token / rate limiting | **NOT ENABLED** | Docs previously claimed it; compiler emits no rate-limit / token-budget CRs. |
| 9 | Auth / provider credentials | **NOT ENABLED** | Clients may send `Bearer demo-key`; no SecurityPolicy / BackendSecurityPolicy enforcement. |
| 10 | Observability Tier1 vs Tier2 | **PARTIAL (new)** | Envoy + SR + demo metrics exist; Tier1/Tier2 decision objects + verify report distinguish them. No separate Prom metric namespaces yet. |

## Friday honesty contract

Every green/live item in the SVP demo must be technically true. Capabilities that are not wired show as **`not enabled`** or **`NOT PROVEN`** — never simulated as active cache/load/P-D decisions.

Verify with:

```bash
token-factory verify phase1 --live
```

See also [architecture.md](architecture.md) Phase 1 section and [svp-demo-script.md](svp-demo-script.md).
