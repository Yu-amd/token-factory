# Routing Policy

## Canonical AMD policy (SHOULD RUN)

The single source of truth for opinionated ranking is **`policies/amd-policy.yaml`**
(policy version **2.4**). See [policy-model.md](policy-model.md) and [policy-evidence.md](policy-evidence.md).

V1 Semantic Router packs live under `policies/profiles/` (compat: `policies/amd-*.yaml`)
and act as **overlays**: objective priorities + domain→endpoint routes — not duplicated
use-case matrices.

## Profile summary

| Profile | Mode | Overlay role |
|---------|------|--------------|
| `amd-balanced` | balanced | Coding → 120B; general → 20B |
| `amd-quality` | quality | Prefer flagship 120B where possible |
| `amd-cost-efficient` | cost | Default to 20B except coding |
| `amd-low-latency` | latency | Prefer 20B for TTFT |
| `amd-edge-first` | edge | Local-first when EPYC/Radeon endpoints configured |
| `amd-enterprise` | enterprise | Strict production lifecycle + reasoning flags |

## Domains

Semantic Router v0.3 uses fixed classifier domains (e.g. `computer science`, `business`, `other`). Each route maps domains → endpoint via `endpoint_ref` and exposes a LoRA name for AI Gateway header matching.

## Reasoning / STEM fallback

When no dedicated reasoning AIM endpoint is configured, the `reasoning_route` (domains: math, physics, chemistry, engineering) falls back to the **coding endpoint** (`gpt-oss-120b-coding` on MI300X). Enable `mock-reasoning` or add a dedicated endpoint in `endpoints.yaml` to override.

## Fallback

`policy.fallback.chain` lists endpoint IDs tried in order when primary backend is unavailable. Eligibility is checked against `catalog/aims.yaml`. Canonical fallback *rules* live in `policies/amd-policy.yaml`; profile chains are V1 execution overlays.

## AMD Opinionated Routing (V2)

V1 profiles above still drive Semantic Router compile. The Opinionated Routing Matrix maps the same profile / `priority_mode` names to **recommendation objectives** (aliases in `catalog/use-cases.yaml`) without changing the gateway path. See [amd-routing-matrix.md](amd-routing-matrix.md) and [policy-model.md](policy-model.md).
