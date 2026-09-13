# Deployment

## Pinned versions

| Component | Version |
|-----------|---------|
| vLLM Semantic Router chart | **0.3.0** (dashboard enabled, port **8700**) |
| Envoy AI Gateway | **v0.3.0** (AIServiceBackend + AIGatewayRoute) |
| Envoy Gateway | **v1.2.3** |
| Prometheus | v2.55.1 |
| Grafana | 11.4.0 |

## Modular install

```bash
export HF_TOKEN=hf_xxx
make preflight
make install              # full stack
# or step-by-step:
bash scripts/install-envoy-gateway.sh
bash scripts/install-envoy-ai-gateway.sh
make compile
bash scripts/install-semantic-router.sh
bash scripts/apply-generated.sh
bash scripts/install-observability.sh
```

## Kind / local cluster

Parent workflow creates the kind cluster. After install:

```bash
make ports    # tracked port-forwards (8080, 8081, 8700, 3000, 9090)
make verify
```

## Mock backends (no GPU)

```bash
bash scripts/install-all.sh --mock-backends
```
