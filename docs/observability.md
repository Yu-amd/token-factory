# Observability

## Stack

- **Prometheus** `v2.55.1` — scrapes Envoy Gateway (`/stats/prometheus:19001`) and Semantic Router (`:9190`)
- **Grafana** `11.4.0` — dashboards:
  - `observability/grafana/token-factory-dashboard.json` (gateway / SR traffic)
  - `observability/grafana/token-factory-automated-demo.json` (**Token Factory Automated Demo** — routing-policy validation panels; latency is operational telemetry only)
- **SR Dashboard** — port 8700 for router-specific views (separate from Grafana)

## Automated Demo metrics

Process-local counters (low cardinality — no request UUID labels):

| Metric | Labels |
|--------|--------|
| `token_factory_demo_requests_total` | scenario, use_case, compute_family, model, validation_status |
| `token_factory_demo_validation_total` | same |
| `token_factory_demo_fallback_total` | scenario, use_case, compute_family |
| `token_factory_demo_route_total` | scenario, compute_family, model |

Attributes on each demo request span: `demo_run_id`, `scenario_id`, `request_id`, use case, policy, serving_pattern, lifecycle, model, compute, endpoint, `fallback_used`.

See [automated-demo.md](automated-demo.md). Soft gap: dashboard JSON is importable; live scrape needs a metrics exporter wired to the demo instrumentor.

Prometheus uses a dedicated ServiceAccount with ClusterRole access to list pods in
`envoy-gateway-system` and `vllm-semantic-router-system`. Without that RBAC, Grafana
panels show **No data** even though the datasource is healthy.

## Dashboard panels

- Request rate and p95 upstream latency (`envoy_*`)
- Backend split by Envoy cluster / route rule
- Fallback / 5xx rates
- Placeholder intent mix (wire SR OTel metrics in production)

## Port forwards

```bash
make ports
# Grafana http://localhost:3000 (admin/admin)
# Prometheus http://localhost:9090  → Status → Targets should show envoy-gateway + semantic-router UP
```

Generate traffic before expecting non-zero request-rate panels:

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer demo-key' \
  -d '{"model":"token-factory/auto","messages":[{"role":"user","content":"Hello"}],"max_tokens":16}'
```
