# Token Factory — Build Report (V1)

**Cluster:** kind `token-factory`  
**Repository:** https://github.com/Yu-amd/token-factory  
**Date:** 2026-09-13  
**Status:** V1 handoff — deployed and tested on kind with real MI300X HTTP backends

---

## Status

### What works

- Full stack on kind: Envoy Gateway **v1.6.0**, Envoy AI Gateway **v0.4.0**, Semantic Router chart **0.3.0**
- Config-driven compile → `generated/` Helm values + AI Gateway manifests
- Virtual model **`token-factory/auto`** with semantic routing to real MI300X vLLM endpoints
- Semantic Router **dashboard** enabled and reachable at http://localhost:8700 (`token-factory dashboard` → HTTP 200)
- Grafana (:3000) and Prometheus (:9090) healthy via port-forward
- Python CLI, Makefile, unit tests (10 passed), CI workflow
- Three operational views: Token Factory UI (`make ui`, live AIM streaming), SR dashboard (:8700), Grafana (:3000)

---

## Architecture

Actual deployed path (verified):

```text
Client (curl / Streamlit / OpenAI SDK)
    │  POST /v1/chat/completions  model=token-factory/auto
    ▼
GatewayClass envoy + EnvoyProxy (ClusterIP)
    ▼
Envoy AI Gateway v0.4.0  (namespace: envoy-ai-gateway-system)
    │  EnvoyPatchPolicy → SR extproc gRPC :50051
    │  AIGatewayRoute ← x-ai-eg-model (real model IDs)
    ▼
vLLM Semantic Router v0.3  (namespace: vllm-semantic-router-system)
    │  domain classify → sets x-ai-eg-model
    ▼
Backend CRD → external vLLM (MI300X public IPs)
    ├─ openai/gpt-oss-120b @ 129.212.183.201:8000
    └─ openai/gpt-oss-20b  @ 165.245.136.245:8000
```

Namespaces:

| Namespace | Components |
|-----------|------------|
| `token-factory` | Gateway, AIGatewayRoute, Backend, EnvoyProxy, policies |
| `envoy-gateway-system` | Envoy Gateway controller + data plane |
| `envoy-ai-gateway-system` | AI Gateway controller |
| `vllm-semantic-router-system` | SR + **semantic-router-dashboard** |
| `observability` | Prometheus, Grafana |

Single source of truth: `config/endpoints.yaml` + `config/policies.yaml` → `token-factory compile` → `generated/`

---

## Component versions

| Component | Exact pin |
|-----------|-----------|
| Token Factory (Python) | 0.1.0 |
| vLLM Semantic Router Helm chart | **0.3.0** (app v0.3.0) |
| SR dashboard image tag | **v0.3.0** |
| Envoy AI Gateway (CRDs + controller) | **v0.4.0** |
| Envoy Gateway + gateway-crds-helm | **v1.6.0** |
| Prometheus | v2.55.1 |
| Grafana | 11.4.0 |
| Python | ≥ 3.11 |
| Kubernetes (kind) | 1.32.x |

---

## Semantic Router Dashboard

| Field | Value |
|-------|-------|
| **Enabled** | `true` (`deploy/helm/vllm-semantic-router/values.yaml` + compiled values) |
| **Deployment** | `semantic-router-dashboard` |
| **Service** | `semantic-router-dashboard` |
| **Port** | **8700/TCP** |
| **URL/access method** | `token-factory dashboard` (discovers Service, tracked port-forward, curl verify) or `token-factory ports start` → http://localhost:8700 |
| **Test result** | HTTP **200**, native vLLM-SR dashboard HTML |
| **Upstream issue** | https://github.com/vllm-project/semantic-router/issues/3751 |
| **Upstream PR** | https://github.com/vllm-project/semantic-router/pull/3752 (commit 291c084) |

**Caveat:** Upstream `vllm-sr dashboard --target k8s` expects ClusterIP Service reachability from the operator host; Token Factory uses `kubectl port-forward` for local access on kind.

**Workaround applied:** Chart 0.3.0 dashboard shares `selectorLabels` with router Service → gRPC :50051 intermittently hits dashboard pods. Patched in `scripts/install-semantic-router.sh` with `token-factory.amd.com/role=router` on Deployment + Service selector.

---

## MI300X environment

SSH inventory completed with local key `~/.ssh/eai_ed25519` (**not committed**).

| Node | Role | OS / GPU | AIM (image 0.11.1) | API |
|------|------|----------|--------------------|-----|
| 165.245.133.102 | Legacy eai kind + Llama AIM (kind net only) | Ubuntu 24.04, MI300X VF, ROCm 7.2.4 | `aim-meta-llama-llama-3-3-70b-instruct` → `amd/Llama-3.3-70B-Instruct-FP8-KV` | On-node `172.18.0.5:8000`; host `:8080` is eai gateway PF. Public `:8000` blocked by cloud firewall |
| 129.212.183.201 | Coding / reasoning | Ubuntu 24.04, MI300X VF | `aim-openai-gpt-oss-120b` → `openai/gpt-oss-120b` | **:8000 public** |
| 165.245.136.245 | General | Ubuntu 24.04, MI300X VF | `aim-openai-gpt-oss-20b` → `openai/gpt-oss-20b` | **:8000 public** |

Token Factory control plane runs on local kind, not on these nodes. Node A still hosts the separate `eai-sr-demo` kind cluster — left intact.

## Models

| Model | Hardware | AIM support (MI300X) | Endpoint | Roles |
|-------|----------|----------------------|----------|-------|
| openai/gpt-oss-120b | Instinct MI300X | optimized | 129.212.183.201:8000 | coding, reasoning/math |
| openai/gpt-oss-20b | Instinct MI300X | optimized | 165.245.136.245:8000 | general |
| mock/reasoning-v1 | (disabled) | — | in-cluster mock | kind demos only |

---

## Routing tests

### Coding

```text
prompt:     "Write a lock-free queue in C++" / "Implement quicksort in Rust"
→ intent:   computer science
→ policy:   amd-balanced / coding_route
→ model:    openai/gpt-oss-120b
→ compute:  Instinct MI300X
→ endpoint: 129.212.183.201:8000
```

### General

```text
prompt:     "What caused the French Revolution"
→ intent:   history / general
→ policy:   amd-balanced / general_route
→ model:    openai/gpt-oss-20b
→ compute:  Instinct MI300X
→ endpoint: 165.245.136.245:8000
```

### Math / reasoning

```text
prompt:     "Solve the integral of x^2 from 0 to 1"
→ intent:   math
→ policy:   amd-balanced / reasoning_route (no dedicated reasoning AIM — uses coding endpoint)
→ model:    openai/gpt-oss-120b
→ compute:  Instinct MI300X
→ endpoint: 129.212.183.201:8000
```

**Policy note:** `lora_name` values are real model IDs (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`) because AIGW `modelNameOverride` does not rewrite request body under dual extproc (SR + AIGW).

---

## Fallback test

| Item | Result |
|------|--------|
| **Deliberate failure** | Primary backend IP patched to 127.0.0.1 |
| **Expected** | Failover to fallback chain (20B general) |
| **Observed** | HTTP **500** when primary broken; cross-model priority failover incorrectly hit the 20B host with a 120B model id (404). Compiler now restricts priority failover to **same-model** replicas only. |
| **Compiler support** | Multi `backendRefs` priority 0/1 + `BackendTrafficPolicy` `/v1/models` health + retry |
| **V2** | Prove end-to-end failover; integrate health-aware routing in policy engine |

---

## Deployment

Clean install (from repo root):

```bash
# 1. Kind cluster (no hostPort 8080)
bash scripts/00-kind-cluster.sh --name token-factory

# 2. Config
cp config/*.example.yaml config/   # skip if config/*.yaml already present
export HF_TOKEN=hf_xxx             # required for SR model downloads

# 3. Python CLI
pip install -e ".[dev,ui,mock]"
make preflight && make compile

# 4. Stack
bash scripts/install-all.sh
# or modular: install-envoy-gateway.sh → install-envoy-ai-gateway.sh →
#              install-semantic-router.sh → apply-generated.sh → install-observability.sh

# 5. Access
token-factory ports start    # or token-factory dashboard
make verify
```

Gateway API test:

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H 'Content-Type: application/json' -H 'Authorization: Bearer demo-key' \
  -d '{"model":"token-factory/auto","messages":[{"role":"user","content":"Hello"}],"max_tokens":64}'
```

Playground live-stream smoke:

```bash
make ports
bash scripts/smoke-playground-stream.sh
make ui   # http://localhost:8501 — caption should show live AIM
```

---

## Known issues

1. **AIGW automatic failover unproven** — priority backendRefs return 500 when primary broken (see Fallback test).
2. **SR chart selector hygiene** — dashboard/router Service selector collision requires post-install patch until upstream chart fix.
3. **gateway-crds Helm Secret limit** — must use server-side apply fallback for CRDs.
4. **No SSH to MI300X** — cannot validate node-local ROCm/AIM versions from this host.
5. **165.245.133.102** — legacy demo stack; do not conflate with Token Factory.
6. **Dual extproc** — `modelNameOverride` gap forces real model IDs in `lora_name` / SR config.

---

## Upstream dependencies

| Dependency | Issue / PR | Impact |
|------------|------------|--------|
| vLLM Semantic Router dashboard | [#3751](https://github.com/vllm-project/semantic-router/issues/3751), [#3752](https://github.com/vllm-project/semantic-router/pull/3752) | Dashboard discoverability; chart selector split |
| Envoy Gateway CRD chart | Secret size limit | Server-side apply workaround |
| Envoy AI Gateway v0.4.0 | modelNameOverride + extproc | lora_name = model ID workaround |

---

## Technical debt

- Policy profiles in `policies/amd-*` should stay synced with `config/policies.yaml` lora naming convention.
- Generated `generated/` gitignored — must run `compile` after config changes.
- Streamlit UI runs locally only (not in-cluster); Playground uses classify→AIM for live TTFT (see `docs/ui.md`).
- Grafana SR intent metrics are Envoy placeholders; wire SR OTel in V2.
- **AIGW SSE buffering** — `stream: true` through the gateway arrives as one burst (TTFT ≈ full generation). Playground uses SR classify → direct AIM stream for live TTFT; gateway live SSE remains a V2 fix.
- `test_policy_profiles_validate` assumes example endpoints exist for all profiles.

---

## V2 note — AMD Opinionated Routing Matrix (additive)

Shipped as an additive layer on V1 (no gateway rebuild):

- Catalogs: `compute.yaml`, `use-cases.yaml`, `models.yaml`, `cost-model.yaml`, `amd-routing-policy.yaml` (`aims.yaml` remains authoritative for GA CAN RUN)
- Extensions: `aims-tech-preview.yaml` (MI350P TP), `model-aliases.yaml`, lifecycle modes, **Lowest-Cost Sufficient**, Radeon Preview lifecycle=`preview`
- Engine + CLI: `token_factory.routing_matrix` / `token-factory recommend --lifecycle …` / `make recommend`
- UI: **AMD Routing Matrix** — MI350P column, lifecycle selector, Serving Pattern, distinct Best Performance / Balance / Lowest-Cost Sufficient cards; mark legend + private-eval note **above** the table; Preview/TP cells tagged `eval` (visible under Production, not blank)
- Docs: [docs/amd-routing-matrix.md](docs/amd-routing-matrix.md), [docs/routing-economics.md](docs/routing-economics.md), [docs/ui.md](docs/ui.md)
- Compile embeds light `routing_matrix` metadata in `ui-metadata.json` (objective alias only)

Thesis: **AIM = CAN**, **Matrix = SHOULD**, **Inventory = CAN ROUTE NOW**, **Lifecycle = GA vs Preview vs Tech Preview**.
Cost ranking is relative — no fabricated $/token or MI350P benchmarks.

## Recommended next (prioritized)

1. **Prove and automate failover** — health-aware routing, AIGW priority path validation, chaos tests.
2. **Remove SR selector patch** — when chart 0.3.x+ fixes dashboard/router Service selectors.
3. **Dedicated reasoning endpoint** — when AIM reasoning model deployed; update `reasoning_route` endpoint_ref.
4. **SSH / node agent** — MI300X inventory beyond HTTP (ROCm version, GPU telemetry).
5. **AIGW body rewrite** — eliminate lora_name = model ID hack when upstream supports dual extproc override.
6. **In-cluster Token Factory UI** — optional Deployment with ServiceAccount RBAC.
7. **EPYC / Radeon routes** — edge endpoints in `endpoints.yaml` + `amd-edge-first` profile live test.
8. **Measured token economics** — fill `cost-model.yaml` benchmarks when AMD numbers land (keep relative until then).

---

## Architecture decisions

| Decision | Rationale |
|----------|-----------|
| **Config compiler** | Single source of truth; avoid manual ConfigMap sed patches (eai-sr-demo lesson) |
| **EG v1.6.0 + AIGW v0.4.0** | Semantic Router upstream e2e tested combination |
| **EnvoyProxy ClusterIP** | kind has no LoadBalancer; Gateway stays Programmed |
| **Real model IDs as lora_name** | AIGW modelNameOverride ineffective with SR extproc in path |
| **Backend fqdn + ip** | Compiler supports DNS hostnames and literal IPs for external vLLM |
| **BackendTrafficPolicy in compiler** | Health checks + retry codified, not manual cluster edits |
| **PID-tracked port-forwards** | Avoid blind `pkill kubectl`; dashboard discovery via kubectl |
| **No hostPort 8080 on kind** | Conflicts with standard AI Gateway port-forward |
| **Public IP endpoints in config** | HTTP-verified MI300X vLLM; no SSH on build host |

---

## Workarounds reference

| # | Workaround | WHY | UPSTREAM | WHEN REMOVABLE |
|---|------------|-----|----------|----------------|
| 1 | CRDs via `helm template \| kubectl apply --server-side` | Helm release Secret > 1 MiB | gateway-crds-helm | External release storage or chart split |
| 2 | SR Service selector patch `token-factory.amd.com/role=router` | Dashboard shares selectorLabels; gRPC hits dashboard | SR chart #3751 | Chart fixes component selector |
| 3 | `lora_name` = real model IDs | modelNameOverride + dual extproc gap | AIGW + SR integration | Upstream body rewrite fix |
| 4 | EnvoyProxy ClusterIP | kind LoadBalancer pending | kind / EG defaults | Cloud LB or MetalLB |
| 5 | HTTP-only MI300X inventory | SSH publickey denied | N/A | SSH key or node agent on build host |
