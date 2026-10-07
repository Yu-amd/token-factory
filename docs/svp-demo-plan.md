# SVP Demo Plan — Phase 1 Model Routing + Phase 2 Agent Governance

**Status:** Plan for review · Friday executive demo  
**Principle:** Token Factory owns AMD opinionated workload → model × compute intelligence. Open-source gateways/routers execute policy. ISV components stay replaceable.

---

## 1. Assessment — current request / data path

### What exists today (preserve)

```text
Client (Streamlit Playground / curl / demo runner)
        │  model: token-factory/auto
        ▼
Envoy AI Gateway  (:18080 via port-forward)     ← auth (demo-key), routes
        │  extproc
        ▼
vLLM Semantic Router  (:8081)                   ← classify intent / domain
        │  sets x-ai-eg-model (lora_name = real model id)
        ▼
AIGatewayRoute → AIServiceBackend
        ▼
OpenAI-compatible AIM endpoint                  ← MI300X (config/endpoints.yaml)
```

**Playground live TTFT path (important):** AIGW buffers SSE, so Playground does:

1. `POST SR /api/v1/classify/intent`
2. Resolve endpoint from `generated/ui-metadata.json`
3. Stream **directly** from AIM (`stream: true`) — measured TTFT
4. Fallback to gateway if classify/direct fails

**Policy plane (orthogonal to gateway path):**

| Layer | Role | Source |
|-------|------|--------|
| AIM catalog | CAN RUN | `catalog/aims.yaml` |
| Canonical policy | SHOULD RUN | `policies/amd-policy.yaml` (+ TP-fit gate) |
| Inventory | AVAILABLE NOW | `config/endpoints.yaml` |
| Compiled routes | ACTIVE EXECUTION | profile overlays → SR/AIGW |

**Automated Demo:** scenario packs under `demo/scenarios/` validate classification + policy + fallback + telemetry. Metrics: `token_factory_demo_*` on `:9108` → Prometheus → Grafana dashboard.

**Existing adapters (narrow):** `ClassifyAdapter` / `ChatAdapter` in `src/token_factory/demo/adapters.py` (live + mock). No Agent Gateway, MCP, or A2A peers yet.

### Live compute gap (as of plan writing)

| Item | Finding |
|------|---------|
| New MI300X nodes | `129.212.177.138`, `165.245.131.224`, `129.212.176.75` — MI300X VF, ROCm present, Jupyter `:8888` only |
| Prior backends | `129.212.183.201` / `165.245.136.245` — **down** (HTTP 000) |
| Intended AIM images | `amdenterpriseai/aim-openai-gpt-oss-{20b,120b}:0.11.1` (ungated OpenAI OSS models) |
| Config today | Hard-coded hosts in `config/endpoints.yaml` (must become env-driven) |

### Demo model selection (ungated, AIM-optimized on MI300X)

| Role | Model | Why |
|------|-------|-----|
| Routine / general | `openai/gpt-oss-20b` | Ungated HF; AIM optimized MI300X; fast path |
| Complex coding / reasoning | `openai/gpt-oss-120b` | Ungated HF; AIM optimized MI300X; coding+reasoning routes |
| Spare / failover | third node with `gpt-oss-20b` or hot standby | Demo resilience |

Avoid Llama / Gemma / Mistral-Large for Friday (gated approvals).

---

## 2. Exact files that need to change

### P0 (Friday blockers)

| Area | Files |
|------|-------|
| Config schema | `src/token_factory/config/schema.py`, `config/loader.py`, `config/validator.py` |
| Endpoints / execution targets | `config/endpoints.yaml`, `config/endpoints.example.yaml`, **new** `config/execution-targets.example.yaml`, `.env.example` |
| Compiler | `src/token_factory/compiler/pipeline.py`, `ai_gateway.py`, `semantic_router.py`, `ui_metadata.py` |
| Adapters | **new** `src/token_factory/adapters/` (`base.py`, `gateway.py`, `agent_gateway.py`, `model_router.py`, `model_endpoint.py`, `mcp.py`, `subagent.py`, `telemetry.py`, `registry.py`) |
| Phase 2 governance | **new** `src/token_factory/governance/` (context, decisions, mock agent gateway) |
| Demo | `src/token_factory/demo/adapters.py`, `runner.py`, `observability.py`, **new** `demo/scenarios/svp.yaml`, MCP/A2A mock servers under `demo/peers/` |
| UI | `ui/views/playground.py`, `ui/components/route_flow.py`, `ui/components/route_inspector.py`, `ui/components/request_state.py`, `ui/app.py` |
| Metrics / Grafana | `src/token_factory/demo/metrics_server.py`, `observability.py`, `observability/grafana/*.json`, `deploy/manifests/observability/prometheus.yaml` |
| Tests | `tests/unit/test_routing_matrix.py` (compat), **new** `tests/unit/test_phase2_governance.py`, `tests/unit/test_adapters.py`, `tests/unit/test_execution_targets.py` |
| Docs | `docs/architecture.md`, `docs/ui.md`, `docs/automated-demo.md`, this plan |
| Ops scripts | **new** `scripts/serve-aim-mi300x.sh` (env-driven AIM launch), `scripts/health-execution-targets.sh` |

### Must not break

- Routing Matrix / Policies / RecommendationEngine
- Existing smoke/executive demo packs
- Compile → generated manifests path
- Port-forward manager behavior (LAN bind already added)

---

## 3. Proposed adapter interfaces

```python
# Conceptual — OSS defaults; ISV swaps via config implementation: field

class GatewayAdapter(Protocol):
    def health(self) -> Health: ...
    def chat_completions(self, req: ModelRequest) -> Response | Iterator[bytes]: ...

class AgentGatewayAdapter(Protocol):
    def authorize(self, ctx: RequestContext) -> GovernanceDecision: ...
    def route(self, ctx: RequestContext, decision: GovernanceDecision) -> PeerTarget: ...
    # modes: live | mock | disabled

class ModelRouterAdapter(Protocol):
    def classify(self, text: str) -> Classification: ...
    def select_route(self, classification, policy_hint) -> RouteDecision: ...

class ModelEndpointAdapter(Protocol):
    def health(self) -> EndpointHealth: ...  # reachable, model_available
    def complete(self, req) -> Completion: ...
    def stream(self, req) -> Iterator[StreamEvent]: ...  # TTFT when genuine

class MCPServerAdapter(Protocol):
    def list_tools(self) -> list[Tool]: ...
    def call_tool(self, name: str, args: dict, ctx: RequestContext) -> ToolResult: ...

class SubAgentAdapter(Protocol):
    def invoke(self, task: AgentTask, ctx: RequestContext) -> AgentResult: ...

class TelemetryAdapter(Protocol):
    def emit(self, event: TelemetryEvent) -> None: ...
    def prometheus_text(self) -> str: ...
```

**Registry:** `adapters:` section in config selects implementation + fallback:

```yaml
adapters:
  gateway:
    implementation: envoy_ai_gateway   # OSS default
    fallback: mock
  agent_gateway:
    implementation: mock               # Friday default if agentgateway unstable
    # implementation: agentgateway     # when live
    fallback: mock
  model_router:
    implementation: vllm_semantic_router
    fallback: mock
  model_endpoint:
    implementation: openai_compatible
  mcp:
    implementation: demo_mcp           # open MCP-shaped peer
    fallback: mock
  subagent:
    implementation: demo_a2a
    fallback: mock
  telemetry:
    implementation: prometheus_file
```

**Hard rule:** MCP and A2A adapters are peers of model routing from Agent Gateway — never children of `ModelRouterAdapter`.

---

## 4. Updated config schema

### `execution_targets` (additive; endpoints.yaml remains supported)

```yaml
version: "2"
execution_targets:
  - id: mi300x-coding
    type: model
    provider: amd
    compute: MI300X
    protocol: openai
    endpoint: ${MI300X_CODING_ENDPOINT}    # https://host:8000 or host+port form
    model: ${MI300X_CODING_MODEL}          # openai/gpt-oss-120b
    role: coding
    aim_support: optimized
    auth:
      type: bearer
      token_env: MI300X_CODING_TOKEN       # optional

  - id: mi300x-general
    type: model
    provider: amd
    compute: MI300X
    protocol: openai
    endpoint: ${MI300X_GENERAL_ENDPOINT}
    model: ${MI300X_GENERAL_MODEL}
    role: general
    aim_support: optimized

  - id: demo-mcp-tools
    type: mcp
    protocol: mcp
    endpoint: ${MCP_ENDPOINT}              # default in-process / local :9200
    mode: mock                             # live|mock|disabled

  - id: demo-subagent
    type: a2a
    protocol: a2a
    endpoint: ${A2A_ENDPOINT}
    mode: mock

adapters:
  agent_gateway:
    implementation: mock
    fallback: mock
  model_router:
    implementation: vllm_semantic_router
    fallback: mock

request_defaults:
  principal: engineering.user
  business_unit: Engineering
  policy_pack: amd-balanced
  lifecycle: production
  objective: balanced
```

Env expansion at load time; secrets never committed. Compiler maps `type: model` targets → existing endpoint records for SR/AIGW backward compatibility.

### Request context (Phase 2)

```yaml
request_id: uuid
principal: string
business_unit: string
policy_pack: string
request_type: model | mcp | a2a
intent: string
data_classification: public | internal | confidential
lifecycle: production | evaluation | ...
objective: balanced | quality | ...
```

Decisions stored separately: `governance` vs `routing` (see UX section).

---

## 5. Sequence diagrams

### Phase 1 — Two-Tier vLLM-SR AI Gateway Blueprint

```text
Client / application
        │
        ▼
Ingress / AI Gateway (Envoy AI Gateway)
        │
        ▼
vLLM Semantic Router — model-routing path
   ├─ provider/model routing (classify → domain → lora_name)
   ├─ AMD policy / model × compute selection (canonical + inventory)
   └─ inference optimization (AIM endpoint choice)
        │
        ▼
execution targets
   ├─ MI300X / Instinct hosted models (live)
   └─ optional frontier / SaaS model endpoints (pluggable)
```

Playground Phase 1 live flow (unchanged topology, clearer labels):

```text
CLIENT → AI GATEWAY → vLLM-SR → AMD POLICY → MODEL / MI300X
```

### Phase 2 — Agent Gateway + Semantic Routing Blueprint

```text
Client / agent
        │
        ▼
Agent Gateway
   ├─ AuthN / AuthZ
   ├─ quotas / rate limits
   ├─ policy enforcement
   ├─ tracing / observability
   ├─ MCP / A2A governance
   └─ provider auth
        │
        ├── MODEL REQUEST ──► vLLM Semantic Router
        │                         ├─ intent / classification
        │                         ├─ capability / economics
        │                         ├─ AMD lifecycle / policy
        │                         └─ endpoint selection
        │                                  ▼
        │                         MI300X / other model servers / frontier
        │
        ├── MCP REQUEST ──► MCP servers          (peer — NOT under vLLM-SR)
        │
        └── A2A REQUEST ──► sub-agents           (peer — NOT under vLLM-SR)
```

Playground Phase 2 live flow:

```text
CLIENT / AGENT → AGENT GATEWAY
        ├─ MODEL → vLLM-SR → AMD POLICY → MI300X / frontier
        ├─ MCP   → MCP SERVER
        └─ A2A   → SUB-AGENT
```

---

## 6. SVP demo script (~3–5 minutes)

**Setup:** Phase selector on Playground; Grafana Automated Demo + Phase 2 panels open; health strip green for MI300X targets.

| # | Scenario | Narration | Expected on screen |
|---|----------|-----------|-------------------|
| 0 | Phase 1 warm-up (30s) | “Today Token Factory places models on AMD Instinct.” | Phase 1 flow lights; coding prompt → `gpt-oss-120b` @ MI300X; live TTFT |
| 1 | Routine coding | Engineering user; Phase 2 PASS; model branch | Governance PASS; intent coding; model `gpt-oss-20b` or policy-selected; stream from live MI300X |
| 2 | Complex coding | Same principal; higher capability | Different model tier (`gpt-oss-120b`); inspector shows **why** selection changed |
| 3 | MCP tool | Tool request; MCP policy allow | Branch to MCP peer; **model router not involved** |
| 4 | Sub-agent | Delegation | A2A peer; shared `request_id` / trace |
| 5 | (optional) Deny | Unauthorized MCP | Stops at Agent Gateway; no model execution |

**Pack:** `demo/scenarios/svp.yaml` — deterministic prompts + expected governance/routing assertions.

---

## 7. Implementation plan

### P0 — Friday demo blockers

1. **Live MI300X serving** — pull/run AIM images on new nodes; env-based `execution_targets`; health checks (reachable / model / success / latency / TTFT).
2. **Keep Phase 1 E2E** — compile + Playground + gateway/SR path against new hosts; no hard-coded IPs in committed defaults (example + `.env`).
3. **Adapter interfaces + registry** — OSS defaults; mock fallback; Phase 1 uses gateway + model_router + model_endpoint only.
4. **Mock Agent Gateway** — AuthN/AuthZ/quota/MCP/A2A policy; clear `demo/mock` labeling; `disabled` skips Phase 2.
5. **MCP + A2A peer mocks** — local processes or in-process adapters; never under SR.
6. **Playground Phase selector** — Phase 1 vs Phase 2 flows; governance + routing panels; correlation id.
7. **`svp` scenario pack** + CLI/UI run path.
8. **Metrics** — add Phase 2 counters; keep `token_factory_demo_*`; Grafana panels.
9. **Tests** — Phase 1 compat, gov allow/deny, model/MCP/A2A branching, correlation, fallback, config validation.
10. **Docs** — architecture diagrams + live/mock/pluggable/ISV matrix.

### P1 — strongly desirable before Friday if time

- Real **agentgateway** integration behind same adapter (feature-flagged).
- Open MCP server process (stdio/HTTP) instead of pure in-process mock.
- Live endpoint health strip on Playground (per-target).
- Executive one-pager export of last `request_id` trace.

### P2 — after SVP demo

- Production IAM / OIDC
- Full MCP marketplace / multi-agent planner
- Commercial router/gateway adapters
- Benchmark portal (explicitly out of scope forever for Automated Demo)

---

## 8. Risks and fallback plan

| Risk | Impact | Fallback |
|------|--------|----------|
| AIM image pull / registry auth fails | No live MI300X | Build `rocm/vllm` serve for gpt-oss-*; or temporary mock endpoints with **honest UI label** (last resort — SVP wants live) |
| 120B OOM / slow cold start | Scenario 2 weak | Use 20B for both with policy still showing tier intent; or TP/quant flags |
| agentgateway unstable | Phase 2 blocked | **Mock Agent Gateway** (default) — same UX, labeled demo/mock |
| AIGW SSE buffering | No gateway TTFT | Keep direct-AIM streaming (existing) |
| Port 3000 clash | Grafana confusion | Stay on `:3001` |
| Cloud firewall blocks :8000 | Laptop cannot hit AIM | SSH tunnel / socat from control host; Playground on demo host streams |
| Partial Phase 2 failure | Breaks Phase 1 | Agent gateway `disabled` or fail-open to Phase 1 path only |

**Partial failure rule:** MI300X model path stays live even if MCP/A2A/agentgateway fall back to mock.

---

## 9. Pluggable / live / mock matrix (docs commitment)

| Component | Friday default | Pluggable later |
|-----------|----------------|-----------------|
| AI Gateway | Envoy AI Gateway (live OSS) | commercial API gateway adapter |
| Model router | vLLM-SR (live OSS) | commercial semantic router |
| Agent Gateway | **mock** (or agentgateway if stable) | commercial agent gateway |
| Model endpoints | AIM / OpenAI-compatible on MI300X (live) | frontier SaaS adapter |
| MCP | demo MCP peer (mock/open) | production MCP mesh |
| A2A | demo sub-agent (mock/open) | production A2A runtime |
| Telemetry | Prometheus + Grafana (live OSS) | proprietary observability |

---

## 10. Overnight execution order (unblocked)

1. Land this plan in `docs/svp-demo-plan.md` ✅  
2. Bring up AIM/`gpt-oss` on the three MI300X nodes (env endpoints)  
3. Implement P0 config + adapters + mock Agent Gateway + peers  
4. Wire Playground Phase selector + `svp` pack + metrics  
5. Tests + architecture doc diagrams  
6. End-to-end rehearsal script under `docs/svp-demo-script.md`

**Do not** broad-refactor RecommendationEngine or invent $/token benchmarks.
