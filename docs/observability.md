# Observability

## Stack

- **Prometheus** `v2.55.1` — scrapes Envoy Gateway and Semantic Router pods
- **Grafana** `11.4.0` — dashboard `observability/grafana/token-factory-dashboard.json`
- **SR Dashboard** — port 8700 for router-specific views

## Dashboard panels

- Request rate and p95 upstream latency
- Backend split by Envoy cluster / route rule
- Fallback / 5xx rates
- Placeholder intent mix (wire SR OTel metrics in production)

## Port forwards

```bash
make ports
# Grafana http://localhost:3000 (admin/admin)
# Prometheus http://localhost:9090
```
