# AMD Canonical Routing Policy Model

Token Factory separates four concerns. They must not collapse into one file or one UI panel.

```text
AIM CATALOG            = CAN RUN
AMD CANONICAL POLICY   = SHOULD RUN
RUNTIME INVENTORY      = AVAILABLE NOW
COMPILED ROUTES        = ACTIVE EXECUTION
```

| Layer | Question | Source |
|-------|----------|--------|
| AIM catalog | Can this model run on this accelerator? | `catalog/aims.yaml` (+ tech-preview merge) |
| Canonical policy | Should AMD recommend it for this workload? | **`policies/amd-policy.yaml`** (v2.3) |
| Inventory | Is an endpoint live now? | `config/endpoints.yaml` |
| Compiled routes | What will Semantic Router actually select? | Profile overlay routes → generated SR/AIGW |

The **Routing Matrix** is a scenario projection of the canonical policy.
The **Policies** tab is the human-readable representation of the same policy.
`token-factory recommend` / `policy explain` / simulation all call `RecommendationEngine`.

## Canonical file

**Path:** `policies/amd-policy.yaml`  
**Policy version:** `2.3` (versioned independently of app code)

Defines:

- eligibility / hard gates (AIM support, capabilities, lifecycle, unoptimized ceiling)
- compute positioning (Instinct, MI350P, Radeon, EPYC) with canonical statements
- serving-pattern tendencies and default latency
- objective definitions (Performance / Balance / LCS / latency / throughput / local-first / enterprise)
- fallback rules
- ranking dimensions
- explicit overrides (sparse AMD-style cells)
- provenance pointers

Compatibility: `catalog/amd-routing-policy.yaml` is a redirect shim. Loaders prefer the canonical path.

## Profile overlays

Profiles under `policies/profiles/` (compat also at `policies/amd-*.yaml`) are **overlays**, not independent routing universes:

| Profile | Objective overlay | Lifecycle bias |
|---------|-------------------|----------------|
| `amd-balanced` | balanced | production |
| `amd-quality` | quality (Best Performance) | production |
| `amd-cost-efficient` | token-cost / LCS | production |
| `amd-low-latency` | latency | production |
| `amd-edge-first` | edge-local | production-preview |
| `amd-enterprise` | enterprise | strict production |

Overlays set objective priorities, lifecycle strictness, economic/performance/locality preference, and V1 Semantic Router domain routes / fallback chains. They **must not** duplicate use-case×model×compute override matrices or compute positioning.

## Decision pipeline

```text
Use Case → Capabilities → Eligibility → AIM Candidates → Compute Fit
        → Objective Ranking → Lifecycle → Endpoint Availability → Compiled Route
```

## CLI

```bash
token-factory policy validate
token-factory policy show
token-factory policy explain --use-case coding-assistant --objective balanced \
  --serving-pattern interactive --traffic medium --lifecycle production
token-factory policy coverage
token-factory policy compile --profile amd-balanced
token-factory policy export -o /tmp/policy.json
token-factory policy diff --left amd-balanced --right amd-enterprise
```

## Engine

`src/token_factory/routing_matrix/engine.py` consumes the canonical policy document (flat engine keys + nested metadata). Explain Policy (`src/token_factory/policy/explain.py`) wraps the same engine for seven-step UI/CLI output.

## Related docs

- [amd-routing-matrix.md](amd-routing-matrix.md) — Matrix UX and lifecycle
- [routing-policy.md](routing-policy.md) — V1 SR profile packs
- [routing-economics.md](routing-economics.md) — relative cost language (no fabricated $/token)
