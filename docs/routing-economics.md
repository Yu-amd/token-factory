# Routing economics (Token Factory)

Additive guidance for the Opinionated Routing Matrix. **No fabricated benchmarks** —
no invented tokens/sec, TTFT, $/hour, or $/1M tokens. Measured slots in
`catalog/cost-model.yaml` stay empty until AMD publishes numbers.

Canonical policy (eligibility, compute positioning, objectives, fallback) lives in
[`policies/amd-policy.yaml`](../policies/amd-policy.yaml) — see [policy-model.md](policy-model.md).
This document covers economic *language* and fit dimensions only.

## Core ideas

1. **Cheapest hardware ≠ cheapest token** — at high utilization, high-throughput Instinct
   can win relative token economics even when `hardware_cost_class` is higher.
2. **Largest model ≠ best fit** — ranking uses capability floors + fit scores, not parameter count.
3. **Lifecycle ≠ support level** — GA / Preview / Tech Preview gates eligibility separately
   from optimized / preview / unoptimized / general.

## Capability floor

Each use case has a qualitative floor in `catalog/use-cases.yaml` → `capability_floors`:

| Tier | Meaning |
|------|---------|
| `basic` | Simple chat / classification |
| `standard` | Coding assistant, summarization, local VLM |
| `high` | Enterprise chat, RAG, agents |
| `frontier` | Complex reasoning, repo agents |

**Lowest-Cost Sufficient** picks the cheapest `hardware_cost_class` that **clears** the floor.
Incapable cheap compute never beats a capable more expensive class.

## Fit scores (per cell)

| Fit | Role |
|-----|------|
| `capability_fit` | Meets required/preferred capabilities + floor |
| `performance_fit` | Throughput / concurrency / interactive locality (qualitative) |
| `economic_fit` / Token Economic Fit | Utilization-aware relative economics for the workload |
| `deployment_fit` | Match to use-case typical deployment class |
| `lifecycle_fit` | GA > preview > tech-preview |
| `serving_pattern_fit` | Interactive vs batch/offline affinity |
| `locality_fit` | Data-local / privacy compute affinity |

Selected objective weights these fits; preference labels
(`PERFORMANCE_PREFERRED`, `ECONOMIC_PREFERRED`, `BALANCED_PREFERRED`,
`EDGE_LOCAL_PREFERRED`, `LOCAL_PREFERRED`, `WORKSTATION_PREFERRED`,
`PRIVACY_PREFERRED`, `PRODUCTION_PREFERRED`, `EVALUATION_PREFERRED`)
are advisory tags on Rank #1.

## Traffic / utilization

| Traffic | Economic bias |
|---------|----------------|
| **low** | Prefer EPYC / Radeon / PCIe footprint (MI350P) when capable |
| **medium** | Balanced |
| **high** | Prefer high-throughput Instinct; Radeon loses concurrency contests |

## Hardware continuum

```text
EPYC (CPU) → Radeon (workstation/local) → MI350P (PCIe enterprise) → rack Instinct (MI300X/MI350X/MI355X)
```

Escalation is **policy-explained**, not a fixed failover chain:
local Radeon when capable → MI350P when enterprise PCIe needed → larger Instinct when
capability floor or concurrency requires it.

### Radeon class

Radeon (R9700 / W7900) is **workstation / local / departmental / developer** compute —
privacy- and data-locality-friendly — **not** merely a cheaper GPU.
It can Rank #1 for local/privacy/low–medium concurrency when the AIM is capable.
It loses for large reasoning / high concurrency / enterprise scale.

Radeon Preview AIMs use lifecycle=`preview` (same lifecycle schema as MI350P’s
`tech-preview` — not a second mechanism). Production excludes them by default;
Production + Preview / Evaluation / local modes allow them.

### MI350P

PCIe / OEM enterprise Instinct — between workstation and rack-scale.
Tech Preview AIMs only; visible under private-eval / evaluation lifecycle modes.
Qualitative `hardware_cost_class: high`;
measured costs null.

## Objectives

| Objective | Rank #1 flavor |
|-----------|----------------|
| `quality` / `throughput` | Performance |
| `token-cost` | Relative token economics |
| `lowest-cost-sufficient` | Cheapest class that clears capability floor |
| `edge-local` (**Local / Workstation First**) | Capable Radeon/EPYC over remote Instinct |
| `enterprise` | GA + Instinct bias |
| `balanced` | Blend of fits — **not** MI355X > MI350X > MI300X by generation alone |

## Data locality / privacy

`--data-locality` / UI checkbox prefers compute with `data_local` (Radeon).
If no capable local AIM exists: **"No local candidate satisfies this workload"**.

## Measured schema (future)

`cost-model.yaml` → `measured.benchmarks` accepts optional rows with
`ttft_ms`, `tokens_per_sec`, `concurrency`, `dollars_per_million_tokens`, etc.
Leave empty until real AMD numbers exist.

## Cost language

| Term | Meaning |
|------|---------|
| **Infrastructure Cost Class** | Qualitative HW footprint (`hardware_cost_class`) — not currency |
| **Token Economic Fit** | Workload-relative economic_fit (traffic + serving pattern aware) |
| **Economic Fit for Workload** | Same as Token Economic Fit in UI copy |
| **Cost Evidence** | `MEASURED` / `ESTIMATED` / `RELATIVE` / `UNKNOWN` — never fabricate $/token |

## AMD Compute Positioning (economics)

- **EPYC** — CPU-centric / batch / low-QPS / fleet utilization; **not** a GPU interactive competitor.
  Rises for batch/offline + relaxed latency; does not auto-rise for high-concurrency interactive.
- **Radeon** — local / workstation / privacy; wins when capable + locality preferred.
- **MI350P** — PCIe enterprise; Tech Preview; between workstation and rack Instinct.
