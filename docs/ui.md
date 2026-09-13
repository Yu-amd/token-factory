# Streamlit UI (Playground)

Local operator UI for Token Factory. Launch with:

```bash
make ports    # gateway :18080, SR API :8081, dashboard :8700, Grafana/Prometheus
make ui       # http://localhost:8501  (runs from ui/ so .streamlit/config.toml applies)
# or: token-factory ui
```

## Tabs

| Tab | Purpose |
|-----|---------|
| **Playground** | Compact operator/demo console — live flow, chat, route inspector |
| **Automated Demo** | Scenario packs validating classification, AMD policy, fallback, observability (**not** a benchmark) |
| **AMD Routing Matrix** | Opinionated SHOULD-RUN rankings (Instinct / EPYC / Radeon) + live overlay |
| **Routing** | Compiled domain → AIM routes |
| **Architecture** | Control-path diagram |
| **Endpoints** | Endpoint inventory from compile |
| **Policies** | AMD Opinionated Routing Policy — eligibility, compute positioning, objectives, coverage, Explain Policy |
| **Operations** | Links to SR Dashboard / Grafana / Prometheus |

See [policy-model.md](policy-model.md), [amd-routing-matrix.md](amd-routing-matrix.md), and [automated-demo.md](automated-demo.md).

## Playground layout

Single-screen operator console (~1440×900 without browser-level vertical scroll).
Conversation and Route Inspector scroll internally; the composer stays pinned at the bottom.
Other tabs (Matrix, Policies, …) keep normal page scroll.

| Region | Role |
|--------|------|
| Compact header | Title + virtual model + preferred stream path |
| Health strip | ● Gateway · SR API · SR Dashboard · Grafana · Prometheus (live probes) |
| Live flow (~72–92px) | CLIENT → ENVOY AI GATEWAY → vLLM SEMANTIC ROUTER → AMD POLICY → AIM / AMD COMPUTE |
| Conversation (~70%) | Chat history + sample prompts (`calc(100vh − chrome)` scroll pane) |
| Route Inspector (~30%) | Mini-tabs: **Decision** · **Policy** · **Metrics** (+ Grafana / SR Dashboard links) |

Flow node states (`idle` / `active` / `complete` / `warning` / `failed`) and connector animation are driven by **real request stages** (classify → resolve → first content token → complete), not fake progress timers. TTFT is measured from stream open to the first content token.

Implementation: `ui/views/playground.py`, `ui/components/route_flow.py`, `ui/components/route_inspector.py`, `ui/components/request_state.py`.

## Policies tab

Human-readable view of **`policies/amd-policy.yaml`** (v2.3). Sections include Policy Overview,
Decision Pipeline, Eligibility / Guardrails, AMD Compute Positioning (Instinct / MI350P / Radeon / EPYC),
Objective Profiles, Serving Patterns, Use-Case Coverage, Explain Policy (engine steps 1–7), Fallback,
Canonical vs Runtime, Compiled Routes, and Provenance. Does **not** paste the full Routing Matrix.

Implementation: `ui/views/policies.py`.

## AMD Routing Matrix tab

Opinionated SHOULD-RUN rankings (no fabricated $/token). The tab **opens at the controls**
(no intro hero / policy meta chips). Policy depth lives on the **Policies** tab
([policy-model.md](policy-model.md)). Key UI cues:

- **Controls** — Use Case, Objective, Deployment, Lifecycle, Serving Pattern, Traffic, Data Locality, Show, I Have Compute
- **Summary cards** — distinct selectors: Best Performance / Best Balance / Lowest-Cost Sufficient (plus Best Batch / Best Local when relevant)
- **Legend above the grid** — ★ Preferred · ② ③ · ✓ · ○ · ⊘ · — · ● Live, plus the private-eval note
- **Private-eval superscript** — Preview / Tech Preview cells stay visible under Production (tagged `eval`, not blank); Evaluation shows rank marks + badge
- **Columns** — Instinct (incl. MI350P), EPYC, Radeon (R9700 / W7900)

CLI equivalent: `token-factory recommend` / `make recommend` (see [amd-routing-matrix.md](amd-routing-matrix.md)).

## Playground streaming (live TTFT)

Envoy AI Gateway v0.4.0 typically **buffers** OpenAI `stream: true` until the full
generation finishes, so gateway TTFT ≈ full latency (can be tens of seconds).

The Playground therefore:

1. Classifies the prompt via Semantic Router  
   `POST {TF_SR_API_URL}/api/v1/classify/intent` (~100ms)
2. Resolves host/model from `generated/ui-metadata.json`
3. Streams **directly** from the AIM OpenAI endpoint (`stream: true`)
4. Falls back to the gateway path if classify/direct AIM fails

The UI labels the path honestly:

- **direct AIM** — SR classify → AIM stream (default when `TF_PLAYGROUND_DIRECT_STREAM=1`)
- **gateway SSE** — full gateway path (forced with `TF_PLAYGROUND_DIRECT_STREAM=0`, or after fallback)
- Fallback shows a warning on the Gateway node plus the error in Route Inspector

Verified: classify ~100ms + AIM TTFT ~0.2s on MI300X public AIMs.

Caption after a reply looks like:

`routed model=openai/gpt-oss-120b · … · live AIM · route=coding_route · classify=127ms · TTFT=210ms`

Set `TF_PLAYGROUND_DIRECT_STREAM=0` to force the buffered gateway path (not recommended).

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `TF_GATEWAY_URL` | `http://127.0.0.1:18080` | AI Gateway (status probes / fallback) |
| `TF_SR_API_URL` / `TF_SR_URL` | `http://127.0.0.1:8081` | SR classification API |
| `TF_VIRTUAL_MODEL` | `token-factory/auto` | Virtual model id (gateway path) |
| `TF_MAX_TOKENS` | `4096` | Completion length |
| `TF_CHAT_TIMEOUT` | `300` | HTTP timeout (seconds) |
| `TF_PLAYGROUND_DIRECT_STREAM` | `1` | `1` = classify→AIM; `0` = gateway only |

Copy `.env.example` → `.env` for local overrides (do not commit secrets).

## Requirements

- `token-factory ports start` so SR API `:8081` is up (needed for classify)
- AIM backends reachable from the operator host (public `:8000` in the test env)
- `make compile` so `generated/ui-metadata.json` has routes/endpoints

## Smoke test

```bash
bash scripts/smoke-playground-stream.sh
```
