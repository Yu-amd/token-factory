# Observability

## Stack

- **Prometheus** `v2.55.1` — scrapes Envoy Gateway (`/stats/prometheus:19001`) and Semantic Router (`:9190`)
- **Grafana** `11.4.0` — dashboard `observability/grafana/token-factory-dashboard.json`
- **SR Dashboard** — port 8700 for router-specific views (separate from Grafana)

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
