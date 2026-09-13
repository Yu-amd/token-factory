# Deployment

## Pinned versions

| Component | Version |
|-----------|---------|
| vLLM Semantic Router chart | **0.3.0** (dashboard enabled, port **8700**) |
| Envoy AI Gateway | **v0.4.0** (AIServiceBackend + AIGatewayRoute) |
| Envoy Gateway + gateway-crds-helm | **v1.6.0** |
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

```bash
bash scripts/00-kind-cluster.sh --name token-factory
```

**Important:** The kind config does **not** map hostPort 8080 (reserved for `kubectl port-forward` to the AI Gateway). Optional high ports 30080/30090 only.

After install:

```bash
make ports    # tracked port-forwards (8080, 8081, 8700, 3000, 9090)
make verify
```

## Mock backends (no GPU)

```bash
bash scripts/install-all.sh --mock-backends
```
