# Automated Demo

> **The Token Factory Automated Demo validates routing-policy execution and observability. It is not a benchmark framework. Runtime latency and token metrics may be observed operationally, but demo traffic must not be used to make comparative hardware performance claims.**

## Purpose

Answer:

> Given a representative mix of enterprise AI requests, does Token Factory correctly classify the workload, apply AMD opinionated routing policy, select an eligible model × compute target, route to a healthy endpoint, execute fallback correctly when needed, and emit the expected telemetry?

It does **not** answer which GPU is fastest, which CPU beats which GPU, or which model “wins.”

## Architecture

```text
Synthetic Workload
      ↓
AI Gateway
      ↓
Semantic Router
      ↓
AMD Opinionated Routing Policy
      ↓
Runtime Endpoint
      ↓
AIM
      ↓
Observability
```

Validation compares:

```text
Expected policy outcome
      ↕
Actual runtime outcome
      ↓
Validation result (PASS / WARN / FAIL / N/A)
```

Dimensions: **Classification · Policy · Capability · Lifecycle · Route · Endpoint · Telemetry**

Canonical preferred vs runtime selected are shown distinctly (preferred-not-deployed is valid when the highest-ranked healthy deployed eligible candidate is chosen).

## Product boundaries

| Concept | Role |
|---------|------|
| Routing policy | AMD opinionated workload → model → hardware mapping (authoritative) |
| Benchmark inputs | Future evidence that may inform policy externally — separate |
| Automated Demo | Validates that policy is **executed** correctly |
| Observability | Evidence of what happened at runtime |

The demo runner **never** auto-tunes policy from synthetic results.

## Scenario packs

Declarative YAML under `demo/scenarios/`:

| Pack | Purpose |
|------|---------|
| `smoke` | 8–12 requests covering coding, reasoning, general, batch, local, multimodal, fallback, lifecycle |
| `executive` | Story sequence (Instinct coding, Radeon local, EPYC batch tendency, reasoning, VLM, fallback, TP exclusion) |
| `enterprise-mixed` | Seeded mixed distribution |
| `observability` | Telemetry attribute validation |
| `fallback` | Preferred-endpoint unavailable injection |

Expectations prefer soft eligibility (capability, family tendency, production-eligible) over brittle exact model×HW matches.

### Request count (`--requests` / UI “Requests to run”)

`--requests N` (and the UI control) is a **target workload size**, not merely a ceiling on a tiny pack:

- **Mixed** packs (`mix` / `generate_count`, e.g. `enterprise-mixed`): generate **N** weighted samples. Pack YAML `generate_count` is the **default** when `--requests` is omitted.
- **Fixed** packs (`smoke`, `executive`, …): cycle the scenario list (stable prompt variants via index) until **N** requests, so any pack can drive a longer Grafana demo.

Always clamped to **8000**. Default in the UI is 40.

## CLI

```bash
token-factory demo list
token-factory demo plan --pack smoke
token-factory demo run --pack smoke --mock
token-factory demo run --pack executive --mock
token-factory demo run --pack enterprise-mixed --seed 42 --mock
token-factory demo run --pack observability --mock
token-factory demo run --pack fallback --mock

# Target request count (cycle/expand pack to fill)
token-factory demo run --pack enterprise-mixed --requests 500 --seed 42 --mock --traffic medium
token-factory demo run --pack smoke --requests 200 --mock

# Failure injection (runtime overlay only)
token-factory demo run --pack smoke --inject preferred-endpoint-unavailable --mock

# CI — exit 0 when policy validations pass; do not fail on “slow” latency
token-factory demo run --pack smoke --ci --mock
```

Optional flags: `--lifecycle`, `--traffic`, `--requests`, `--concurrency`, `--seed`, `--inject`, `--live`.

Artifacts: `generated/demo-runs/<run-id>.json`

## UI

Tab order: **Playground | Automated Demo | AMD Routing Matrix | …**

Controls: pack, lifecycle, traffic profile, failure-injection checkboxes, **Requests to run** (target count; packs cycle/expand to fill), planned-count preview, Run Demo.

Sections: Run Summary, Current Request, Live feed, routing/model/use-case **distributions** (coverage, not performance), Validation results, Observability links, recent run history.

## Observability

Propagated attributes (spans / request telemetry):

`demo_run_id`, `scenario_id`, `request_id`, use case, policy, `serving_pattern`, `lifecycle`, model, compute, endpoint, `fallback_used`

Prometheus-style counters (low cardinality — **no request UUID labels**):

- `token_factory_demo_requests_total`
- `token_factory_demo_validation_total`
- `token_factory_demo_fallback_total`
- `token_factory_demo_route_total`

Labels: `scenario`, `use_case`, `compute_family`, `model`, `validation_status`

### Grafana

Dashboard definition: [`observability/grafana/token-factory-automated-demo.json`](../observability/grafana/token-factory-automated-demo.json) — **Token Factory Automated Demo**.

**Soft gap:** the dashboard JSON is shipped for import. Live panels require Prometheus scrape of demo counters (process-local instrumentor today; wire to a `/metrics` exporter when deploying the control-plane metrics endpoint). Gateway latency panels reuse existing Envoy metrics as operational context only.

## Failure injection

Demo-only overlay (never mutates canonical policy or on-disk endpoints):

- Preferred endpoint unavailable
- No Radeon / No EPYC / No local / No Instinct
- Force lifecycle restriction (production)

## Safety

- Max requests per run: **8000** (target count; packs cycle/expand up to this bound)
- Max concurrency: **10**
- Not a stress-testing or benchmark platform
