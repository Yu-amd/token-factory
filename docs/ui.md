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
| **Playground** | Chat with live token streaming |
| **Routing** | Compiled domain → AIM routes |
| **Architecture** | Control-path diagram |
| **Endpoints** | Endpoint inventory from compile |
| **Policies** | Active policy pack |
| **Operations** | Links to SR Dashboard / Grafana / Prometheus |

## Playground streaming (live TTFT)

Envoy AI Gateway v0.4.0 typically **buffers** OpenAI `stream: true` until the full
generation finishes, so gateway TTFT ≈ full latency (can be tens of seconds).

The Playground therefore:

1. Classifies the prompt via Semantic Router  
   `POST {TF_SR_API_URL}/api/v1/classify/intent` (~100ms)
2. Resolves host/model from `generated/ui-metadata.json`
3. Streams **directly** from the AIM OpenAI endpoint (`stream: true`)
4. Falls back to the gateway path if classify/direct AIM fails

Verified: classify ~100ms + AIM TTFT ~0.2s on MI300X public AIMs.

Caption after a reply looks like:

`routed model=openai/gpt-oss-120b · … · live AIM · route=coding_route · classify=127ms`

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
