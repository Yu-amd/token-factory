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
- **Streamlit UI** — Playground with **live TTFT**, **Automated Demo**, **AMD Routing Matrix**, **Policies** (canonical policy explorer), routing, architecture, inventory, operations
- **AMD Opinionated Routing** — one canonical policy (`policies/amd-policy.yaml`) shared by Matrix, Explain Policy, simulation, and compile (`token-factory recommend` / `token-factory policy` / `token-factory evidence`) — see [docs/policy-evidence.md](docs/policy-evidence.md)
- **Automated Demo** — declarative scenario packs that validate classification, policy, fallback, and observability (`token-factory demo`) — **not** a benchmark portal
- **Mock OpenAI backends** for kind/CI without GPU
- **Clean port-forward manager** with PID tracking (no blind `pkill kubectl`)

## Automated Demo

Routing-policy and observability validation for representative enterprise AI traffic:

```bash
token-factory demo plan --pack smoke
token-factory demo run --pack smoke --mock          # CI-friendly mocks
token-factory demo run --pack executive --mock
token-factory demo run --pack smoke --ci --mock     # exit 0 on policy PASS
```

Validates classification, AMD canonical policy eligibility, lifecycle, capability, route/endpoint selection, fallback injection, and telemetry attributes. Latency may be recorded as telemetry only — never as comparative hardware claims.

Demo counters (`token_factory_demo_*`) are served on **`:9108/metrics`** (`make ui` starts the metrics server; Prometheus job `token-factory-demo` scrapes it). Grafana **Token Factory Automated Demo** panels use those series — no SR intent placeholder. Details: [docs/automated-demo.md](docs/automated-demo.md), [docs/observability.md](docs/observability.md).

## AMD Opinionated Routing

Token Factory V1 knows what is **deployed** and how Semantic Router classifies a request.
V2 adds an opinionated matrix on top of the authoritative AIM catalog — without replacing the gateway path:

```text
AIM CATALOG            = CAN RUN      (catalog/aims.yaml)
AMD CANONICAL POLICY   = SHOULD RUN   (policies/amd-policy.yaml v2.4)
RUNTIME INVENTORY      = AVAILABLE NOW (config/endpoints.yaml)
COMPILED ROUTES        = ACTIVE EXECUTION (profile overlays → SR / AIGW)
```

| Concept | Meaning | Source |
|---------|---------|--------|
| **AIM** | CAN RUN | `catalog/aims.yaml` |
| **Canonical policy** | SHOULD RUN | `policies/amd-policy.yaml` + engine |
| **Inventory** | AVAILABLE NOW | `config/endpoints.yaml` |
| **Profiles** | Overlays | `policies/profiles/amd-*.yaml` (objective / lifecycle / V1 routes) |

Use cases, compute metadata, model capabilities, and a relative (non-fabricated) cost model live under `catalog/`. Rankings are produced by `RecommendationEngine` and surfaced in:

- UI **AMD Routing Matrix** (`make ui`) — **Portfolio Matrix** (full AIM catalog) or **Executive View** (truncated); controls → cards → coverage strip → legend → scrollable grid; **Policies** tab for canonical policy depth
- CLI: `token-factory recommend --use-case coding-assistant --objective balanced`
- CLI: `token-factory catalog audit` / `token-factory matrix audit`
- CLI: `token-factory policy show|explain|coverage|validate`
- Makefile: `make recommend`

Details: [docs/policy-model.md](docs/policy-model.md), [docs/amd-routing-matrix.md](docs/amd-routing-matrix.md), [docs/aim-catalog.md](docs/aim-catalog.md).

### AMD Compute Positioning

- **EPYC** — CPU-centric / batch / low-QPS / fleet utilization — **not** a GPU interactive competitor; rises for batch/offline + relaxed latency; does not auto-rise for high-concurrency interactive.
- **Radeon** — local / workstation / privacy when capable.
- **MI350P** — PCIe enterprise Tech Preview; private-eval visibility; never silent GA.
- Summary cards use **distinct selectors** (Performance / Balance / Lowest-Cost Sufficient).
Economics, capability floors, MI350P Tech Preview, and Radeon Preview:
[docs/routing-economics.md](docs/routing-economics.md).

**MI350P** (PCIe Instinct) and **Radeon Preview** AIMs are lifecycle-gated
(`tech-preview` / `preview`) — never silent production GA. Use
`token-factory recommend --lifecycle evaluation` or the Matrix lifecycle selector
for evaluation; production defaults exclude them.

## Architecture

```
Client (curl / Streamlit)
    │  model: token-factory/auto
    ▼
Envoy AI Gateway (v0.4.0)     auth, rate limits, AIGatewayRoute
    │  extproc gRPC
    ▼
vLLM Semantic Router (0.3.0)  domain classify → LoRA / x-ai-eg-model
    │         ├─ coding / math  → GPT-OSS 120B (Instinct)
    │         └─ general        → GPT-OSS 20B (Instinct)
    ▼
Prometheus / Grafana / SR Dashboard :8700
```

**Playground note:** AI Gateway buffers SSE until generation completes. The Streamlit
Playground classifies via SR API (`:8081`) then streams **directly from AIM** for
live TTFT. See [docs/ui.md](docs/ui.md).

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
make ports                   # 18080 gateway, 8081 SR API, 8700 dashboard, 3000/9090
make ui                      # Streamlit on :8501 (live AIM streaming)
bash scripts/smoke-playground-stream.sh   # classify → AIM TTFT smoke
```

### Test routing (gateway path)

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer demo-key' \
  -d '{"model":"token-factory/auto","messages":[{"role":"user","content":"Write quicksort in Rust"}],"max_tokens":64}'
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
catalog/aims.yaml       AMD AIM support matrix (CAN RUN)
catalog/*               AIM / use-cases / compute / models / cost (CAN RUN + metadata)
policies/amd-policy.yaml Canonical AMD routing policy (SHOULD RUN, v2.4)
policies/profiles/      Profile overlays (objective + V1 SR routes)
src/token_factory/      Python package (CLI, compiler, catalog, routing_matrix)
deploy/                 Helm values + K8s manifests
scripts/                Modular install/apply/uninstall
generated/              Compiler output (gitignored content)
tests/                  Unit tests + mock backends
ui/                     Streamlit app (Playground + AMD Routing Matrix)
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
| `token-factory recommend` | AMD Opinionated Routing recommendations |
| `token-factory policy …` | validate / show / explain / coverage / compile / export / diff |
| `token-factory demo …` | Automated Demo plan / run / list (policy validation, not benchmarks) |
| `token-factory ui` | Launch Streamlit |

## Makefile targets

`help`, `preflight`, `compile`, `install`, `apply`, `verify`, `test`, `demo`, `status`, `dashboard`, `grafana`, `ports`, `ui`, `smoke-ui`, `recommend`, `logs`, `reset`, `uninstall`, `update-aim-catalog`, `lint`

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
- [AMD Canonical Policy Model](docs/policy-model.md) — CAN / SHOULD / AVAILABLE / ACTIVE
- [AMD Opinionated Routing Matrix](docs/amd-routing-matrix.md) — Matrix UX and lifecycle
- [Configuration](docs/configuration.md)
- [Deployment](docs/deployment.md)
- [Streamlit UI / Playground](docs/ui.md)
- [Automated Demo](docs/automated-demo.md) — routing-policy & observability validation (not a benchmark)
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
