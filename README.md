# AMD Token Factory

Reference architecture for **config-driven Mixture-of-Models (MoM)** inference on AMD compute (Instinct, EPYC, Radeon) using [vLLM Semantic Router v0.3](https://github.com/vllm-project/semantic-router) and [Envoy AI Gateway v0.4.0](https://github.com/envoyproxy/ai-gateway).

Repository: https://github.com/Yu-amd/token-factory

## Features

- **Single virtual model**: `token-factory/auto`
- **Single source of truth**: `endpoints.yaml` + `policies.yaml` + `catalog/aims.yaml` → compiler → `generated/`
- **Pinned stack**: SR chart 0.3.0 (dashboard **enabled**, port **8700**), AIGW v0.4.0, Envoy Gateway v1.6.0
- **Python CLI** (`token-factory`): preflight, compile, install, verify, ports, UI, route explain
- **Policy profiles**: balanced, quality, cost-efficient, low-latency, edge-first, enterprise
- **AIM catalog** from AMD Enterprise AI accelerator matrix
- **Streamlit UI** with chat, routing, architecture, inventory, operations
- **Mock OpenAI backends** for kind/CI without GPU
- **Clean port-forward manager** with PID tracking (no blind `pkill kubectl`)

## Architecture

```
Client (curl / Streamlit)
    │  model: token-factory/auto
    ▼
Envoy AI Gateway (v0.4.0)     auth, rate limits, AIGatewayRoute
    │  extproc gRPC
    ▼
vLLM Semantic Router (0.3.0)  domain classify → LoRA / x-ai-eg-model
    │         ├─ coding-expert  → GPT-OSS 120B (Instinct)
    │         └─ general-expert → GPT-OSS 20B (Instinct)
    ▼
Prometheus / Grafana / SR Dashboard :8700
```

See [docs/architecture.md](docs/architecture.md).

## Quick start

### Prerequisites

- Python **≥ 3.11**
- Kubernetes 1.28+ (kind/k3d for local)
- Helm **3.14+**, kubectl
- HuggingFace token for Semantic Router model downloads

### Install CLI

```bash
cd Token_Factory
pip install -e ".[dev,ui,mock]"
cp config/token-factory.example.yaml config/token-factory.yaml
cp config/endpoints.example.yaml config/endpoints.yaml
cp config/policies.example.yaml config/policies.yaml
export HF_TOKEN=hf_xxx
make preflight
make compile
```

### Deploy stack (cluster required)

```bash
make install                 # full modular install
make verify
make ports                   # 8080 gateway, 8081 SR API, 8700 dashboard, 3000/9090
make ui                      # Streamlit on :8501
```

### Test routing

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"token-factory/auto","messages":[{"role":"user","content":"Write quicksort in Rust"}]}'
```

## Version matrix

| Component | Pin |
|-----------|-----|
| Semantic Router Helm chart | **0.3.0** (app v0.3.0) |
| SR Dashboard | enabled, port **8700** |
| Envoy AI Gateway | **v0.4.0** |
| Envoy Gateway + gateway-crds-helm | **v1.6.0** |
| Prometheus | v2.55.1 |
| Grafana | 11.4.0 |
| Python | ≥ 3.11 |

## Repository layout

```
config/                 Example + active YAML config
policies/               amd-* routing profiles
catalog/aims.yaml       AMD AIM support matrix
src/token_factory/      Python package (CLI, compiler, catalog)
deploy/                 Helm values + K8s manifests
scripts/                Modular install/apply/uninstall
generated/              Compiler output (gitignored content)
tests/                  Unit tests + mock backends
ui/                     Streamlit app
observability/          Grafana dashboard JSON, Prometheus rules
docs/                   Architecture, deployment, ops guides
```

## CLI commands

| Command | Description |
|---------|-------------|
| `token-factory preflight` | Validate toolchain + config |
| `token-factory compile` | Generate Helm values + manifests |
| `token-factory install` | Run full install script |
| `token-factory apply` | Compile + kubectl apply |
| `token-factory verify` | Check key deployments |
| `token-factory status` | HTTP health probes |
| `token-factory ports start\|stop\|list` | Tracked port-forwards |
| `token-factory route-explain "..."` | Heuristic route explanation |
| `token-factory catalog-update` | Refresh catalog metadata timestamp |
| `token-factory ui` | Launch Streamlit |

## Makefile targets

`help`, `preflight`, `compile`, `install`, `apply`, `verify`, `test`, `demo`, `status`, `dashboard`, `grafana`, `ports`, `ui`, `logs`, `reset`, `uninstall`, `update-aim-catalog`, `lint`

## Example endpoints (reference)

| ID | Host | Model |
|----|------|-------|
| gpt-oss-120b-coding | 129.212.183.201:8000 | openai/gpt-oss-120b |
| gpt-oss-20b-general | 165.245.136.245:8000 | openai/gpt-oss-20b |

Override in `config/endpoints.yaml` for your environment.

## Namespaces

| Namespace | Workloads |
|-----------|-----------|
| `token-factory` | Gateway CRs, mock backends |
| `envoy-gateway-system` | Envoy Gateway |
| `envoy-ai-gateway-system` | AI Gateway controller |
| `vllm-semantic-router-system` | SR + **dashboard :8700** |
| `observability` | Prometheus, Grafana |

## Development

```bash
make test
make lint
make demo    # local mock backend
```

CI (`.github/workflows/ci.yml`): ruff, pytest, compile, Helm template dashboard verification.

## Documentation

- [BUILD_REPORT.md](BUILD_REPORT.md) — V1 verified status, routing tests, workarounds
- [Configuration](docs/configuration.md)
- [Deployment](docs/deployment.md)
- [Semantic Router Dashboard](docs/semantic-router-dashboard.md)
- [Routing policies](docs/routing-policy.md)
- [AMD compute / AIMs](docs/amd-compute-guide.md)
- [Observability](docs/observability.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Security](docs/security.md)
- [Test environment notes](docs/test-environment.md)
- [eai-sr-demo parity](docs/eai-sr-demo-parity.md)

## License

Apache-2.0 — see [LICENSE](LICENSE).
