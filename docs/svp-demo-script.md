# SVP Demo Script (3–5 minutes)

**Host:** control laptop with Token Factory UI  
**Compute:** live MI300X AIM endpoints (env-configured)

| Role | Model | Example endpoint env |
|------|-------|----------------------|
| Complex coding | `openai/gpt-oss-120b` | `MI300X_CODING_HOST` |
| Routine / general | `openai/gpt-oss-20b` | `MI300X_GENERAL_HOST` |
| Spare | `openai/gpt-oss-20b` | `MI300X_SPARE_HOST` |

## Prep (T−15)

```bash
make ports
make ui   # http://localhost:8501  (LAN: http://<host-ip>:8501)
# Grafana :3001  SR dashboard :8700
# Honest Phase 1 architecture check (run before SVP)
token-factory verify phase1 --live

token-factory demo plan --pack svp
```

Health strip: Gateway · SR · Grafana green. Spot-check:

```bash
curl -sS http://$MI300X_CODING_HOST:8000/v1/models | head
curl -sS http://$MI300X_GENERAL_HOST:8000/v1/models | head
```

## Storyboard

### 0 — Phase 1 (30s)

1. Playground → **Phase 1 — Model Routing**
2. Prompt: “Write a ROCm kernel sketch in Python”
3. Point at live flow: `CLIENT → AI GATEWAY → vLLM-SR → AMD POLICY → MODEL / MI300X`
4. Call out live TTFT + model id on Instinct

**Line:** “Phase 1 answers *where* the model runs — AMD policy onto live MI300X.”

### 1 — Routine coding (Phase 2)

1. Switch to **Phase 2 — Agent + Model Governance**
2. Automated Demo pack **svp** scenario 1, or Playground prompt for Fibonacci
3. Show **Governance** PASS (AuthN/AuthZ/Quota) then **Routing** (intent → model → MI300X)

### 2 — Complex coding

1. Lock-free C++ queue prompt (scenario 2)
2. Show selection shift to `gpt-oss-120b` / coding endpoint
3. **Why changed:** capability / objective — not a benchmark claim

### 3 — MCP tool

1. Scenario 3 — `repo_search`
2. Flow branches to **MCP SERVER**
3. Explicit: “Model router is not on this path.”

### 4 — Sub-agent

1. Scenario 4 — A2A delegation
2. Show shared `request_id` / trace

### 5 — Optional deny

1. Scenario 5 — denied MCP tool
2. Stops at Agent Gateway — no model execution

## Closing line

“Phase 1 places models on AMD Instinct. Phase 2 governs the agent graph — models, tools, and sub-agents as peers — with open-source defaults and replaceable adapters.”

## Phase 1 honesty check (before SVP)

```bash
token-factory verify phase1 --live
```

Expect **Overall demo readiness: PASS WITH LIMITATIONS**. Green items must be
true; KV/prefix/P-D, rate limiting, and gateway auth show **NOT ENABLED**.
Same-model failover shows **CONFIGURED** when the 20b spare is in inventory;
cross-model fallback stays **NOT PROVEN**.

See [phase1-architecture-gap.md](phase1-architecture-gap.md).

## Fallback if something is red

| Failure | Action |
|---------|--------|
| Agent Gateway / MCP / A2A | Stay on mock adapters (labeled); Phase 1 still live |
| One MI300X down | Use spare node / other role endpoint |
| Gateway SSE | Keep Playground direct-AIM streaming |
