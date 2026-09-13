# Test Environment

Verified control plane on **kind cluster `token-factory`** (build host), routing to **DigitalOcean MI300X AIM endpoints**.

SSH inventory completed with key at `~/.ssh/eai_ed25519` (local only — **never committed**).

## Kind cluster (control plane)

| Item | Value |
|------|-------|
| Cluster name | `token-factory` |
| Create script | `scripts/00-kind-cluster.sh` |
| Port mapping | **No hostPort 8080** (conflicts with gateway port-forward) |
| GatewayClass | `envoy` + EnvoyProxy **ClusterIP** |

## Stack versions (verified)

| Component | Version |
|-----------|---------|
| Envoy Gateway + gateway-crds-helm | **v1.6.0** (CRDs via server-side apply) |
| Envoy AI Gateway | **v0.4.0** |
| vLLM Semantic Router chart | **0.3.0**, `dashboard.enabled=true` |
| AIM images | `amdenterpriseai/...:0.11.1` |

## Observability (verified)

| Service | Local URL | Result |
|---------|-----------|--------|
| Semantic Router dashboard | http://localhost:8700 | HTTP 200 via `token-factory dashboard` |
| Grafana | http://localhost:3000 | HTTP 200 |
| Prometheus | http://localhost:9090 | healthy |

---

## MI300X nodes (SSH + HTTP)

All three: **Ubuntu 24.04.4 LTS**, **AMD Instinct MI300X VF** (`gfx942`), ~**697G** root disk, ~**235Gi** RAM, Docker present.

### Node A — `165.245.133.102` (hostname `7`)

| Item | Finding |
|------|---------|
| ROCm | **7.2.4** |
| GPU | 1× MI300X VF (VRAM ~90% in use) |
| Free disk | ~483G |
| AIM | `vllm-llama` → `amdenterpriseai/aim-meta-llama-llama-3-3-70b-instruct:0.11.1` |
| Model | `amd/Llama-3.3-70B-Instruct-FP8-KV` (also exposed as LoRA aliases `math-expert`, `science-expert`, …) |
| Network | Container on **kind** bridge `172.18.0.5:8000` (not published to host by Docker) |
| Also running | `eai-demo` kind cluster (k8s **v1.32.2**); host `:8080` = kubectl PF to legacy eai/SR gateway (`MoM` / `vllm-sr/auto`) |
| Token Factory role | **Do not use as TF control plane.** Llama AIM is on-node only unless published; public TF backends are B/C |

Token Factory optional note: a `socat` forward `0.0.0.0:8000 → 172.18.0.5:8000` was installed for local on-node access (`/var/run/token-factory-llama-8000.pid`). **External** reachability to `:8000` remains blocked (cloud/firewall); do not open broad firewall rules for demos.

### Node B — `129.212.183.201`

| Item | Finding |
|------|---------|
| Hostname | `rocm-10-0-gpu-mi300x1-192gb-devcloud-atl1` |
| GPU | 1× MI300X VF |
| Free disk | ~546G |
| AIM | `vllm-gpt-oss-120b` → `amdenterpriseai/aim-openai-gpt-oss-120b:0.11.1` |
| Model | `openai/gpt-oss-120b` on **`:8000`** (public) |
| Also | `rocm` container on `:8888` |
| K8s | none |
| Token Factory role | **Coding + reasoning** backend |

### Node C — `165.245.136.245`

| Item | Finding |
|------|---------|
| Hostname | `rocm-10-0-gpu-mi300x1-192gb-devcloud-atl1` |
| GPU | 1× MI300X VF |
| Free disk | ~531G |
| AIM | `vllm-gpt-oss-20b` → `amdenterpriseai/aim-openai-gpt-oss-20b:0.11.1` |
| Model | `openai/gpt-oss-20b` on **`:8000`** (public) |
| Also | separate `eai-demo` kind cluster (k8s **v1.37.0**) with host ports 30080/30090 |
| Token Factory role | **General** backend |

---

## Verified routing (Token Factory on kind → public AIMs)

Virtual model: `token-factory/auto` (also accepts `MoM` via SR)

| Workload | Example | Model | Endpoint |
|----------|---------|-------|----------|
| Coding | lock-free queue / quicksort / B-tree | `openai/gpt-oss-120b` | 129.212.183.201:8000 |
| General | French Revolution | `openai/gpt-oss-20b` | 165.245.136.245:8000 |
| Math | integral of x² | `openai/gpt-oss-120b` | 129.212.183.201:8000 |

## Workarounds

See `BUILD_REPORT.md` for WHY / UPSTREAM / WHEN REMOVABLE:

1. gateway-crds server-side apply (Helm Secret size)
2. SR Service selector patch (dashboard label collision)
3. `lora_name` = real model IDs (AIGW override + dual extproc)
4. EnvoyProxy ClusterIP on kind
5. Same-model-only priority failover (cross-model rewrite unreliable)

## Secrets

| Item | Location | Committed? |
|------|----------|------------|
| SSH key | `~/.ssh/eai_ed25519` (symlink `~/eai_ed25519`) | **No** |
| HF token | env / cluster Secret `hf-token-secret` | **No** |

## Repository

Private GitHub: https://github.com/Yu-amd/token-factory
