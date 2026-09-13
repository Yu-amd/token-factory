# Routing Policy

Policies live under `policies/` and define how Semantic Router classifies requests.

## Profile summary

| Profile | Mode | Behavior |
|---------|------|----------|
| `amd-balanced` | balanced | Coding → 120B; general → 20B |
| `amd-quality` | quality | Prefer flagship 120B where possible |
| `amd-cost-efficient` | cost | Default to 20B except coding |
| `amd-low-latency` | latency | Prefer 20B for TTFT |
| `amd-edge-first` | edge | Edge-ready when EPYC/Radeon endpoints configured |
| `amd-enterprise` | enterprise | Strict fallback + reasoning flags |

## Domains

Semantic Router v0.3 uses fixed classifier domains (e.g. `computer science`, `business`, `other`). Each route maps domains → endpoint via `endpoint_ref` and exposes a LoRA name for AI Gateway header matching.

## Fallback

`policy.fallback.chain` lists endpoint IDs tried in order when primary backend is unavailable. Eligibility is checked against `catalog/aims.yaml`.
