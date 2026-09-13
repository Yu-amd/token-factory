# Observability

## Stack

- **Prometheus** `v2.55.1` — scrapes:
  - Envoy Gateway (`/stats/prometheus:19001`)
  - Semantic Router (`:9190`)
  - Token Factory Automated Demo host metrics (`172.19.0.1:9108/metrics` via kind bridge)
- **Grafana** `11.4.0` — dashboards:
  - `observability/grafana/token-factory-dashboard.json` (gateway / SR traffic)
  - `observability/grafana/token-factory-automated-demo.json` (**Token Factory Automated Demo** — routing-policy validation panels; latency is operational telemetry only)
- **SR Dashboard** — port 8700 for router-specific views (separate from Grafana)

## Scraped metrics (what exists today)

| Source | Job | Examples |
|--------|-----|----------|
| Envoy AI Gateway | `envoy-gateway` | `envoy_http_downstream_rq_total`, `envoy_cluster_upstream_rq_*`, 5xx class |
| Semantic Router | `semantic-router` | `llm_reasoning_decisions_total` (by `category`), `llm_model_selection_total` (by `model`), latency histograms |
| Automated Demo (host UI/CLI) | `token-factory-demo` | `token_factory_demo_requests_total`, `_validation_total`, `_fallback_total`, `_route_total` |

There is **no** separate “Model Intent Mix” placeholder series. Category/route mix uses
`llm_reasoning_decisions_total{category=…}` from the Semantic Router scrape.

## Automated Demo metrics

Counters (low cardinality — no request UUID labels). Snapshot file
`generated/demo-metrics.prom` is served at `http://127.0.0.1:9108/metrics`
by `python -m token_factory.demo.metrics_server` (started automatically by
`make ui`; `TF_DEMO_METRICS_PORT` overrides the port):

| Metric | Labels |
|--------|--------|
| `token_factory_demo_requests_total` | scenario, use_case, compute_family, model, validation_status, lifecycle |
| `token_factory_demo_validation_total` | same |
| `token_factory_demo_fallback_total` | scenario, use_case, compute_family, lifecycle |
| `token_factory_demo_route_total` | scenario, compute_family, model, lifecycle |

Attributes on each demo request span: `demo_run_id`, `scenario_id`, `request_id`, use case, policy, serving_pattern, lifecycle, model, compute, endpoint, `fallback_used`.

See [automated-demo.md](automated-demo.md).

Prometheus uses a dedicated ServiceAccount with ClusterRole access to list pods in
`envoy-gateway-system` and `vllm-semantic-router-system`. Without that RBAC, Grafana
panels show **No data** even though the datasource is healthy.

If job `token-factory-demo` is **DOWN**, confirm the UI is listening on `:9108` and that
the scrape target matches your kind bridge gateway (`docker network inspect kind`).

## Dashboard panels

**AMD Compute Traffic** (`token-factory-v1`):

- Request rate and p95 upstream latency (`envoy_*`)
- Backend split by Envoy cluster
- Fallback / 5xx rates
- SR category / route mix (`llm_reasoning_decisions_total`)
- SR model selection (`llm_model_selection_total`)

**Automated Demo** (`token-factory-automated-demo`):

- Requests by use case / model / compute family / lifecycle
- Validation pass/fail, fallbacks
- Envoy rate/latency as operational context only

## Port forwards

```bash
make ports
# Grafana http://localhost:3000 (admin/admin)
# Prometheus http://localhost:9090  → Status → Targets should show
#   envoy-gateway + semantic-router + token-factory-demo UP (demo job needs make ui)
```

Generate gateway traffic before expecting non-zero Envoy panels:

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer demo-key' \
  -d '{"model":"token-factory/auto","messages":[{"role":"user","content":"Hello"}],"max_tokens":16}'
```

For Automated Demo panels: `make ui`, open Grafana → Token Factory Automated Demo, run a pack.
