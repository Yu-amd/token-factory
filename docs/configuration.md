# Configuration

## Files

| File | Purpose |
|------|---------|
| `config/token-factory.yaml` | Cluster namespaces, component pins, paths |
| `config/endpoints.yaml` | Backend inventory (host, model, hardware) |
| `config/policies.yaml` | Active routing policy |
| `catalog/aims.yaml` | AMD AIM support matrix |
| `.env` / `.env.example` | Local URLs, Playground streaming knobs |

Copy examples:

```bash
cp config/token-factory.example.yaml config/token-factory.yaml
cp config/endpoints.example.yaml config/endpoints.yaml
cp config/policies.example.yaml config/policies.yaml
cp .env.example .env   # optional local overrides
```

## Compile

```bash
token-factory compile
# outputs under generated/ (gitignored)
# includes semantic-router-values.yaml with global.router.auto_model_name
# and ui-metadata.json used by the Streamlit Playground
```

## Validation

```bash
token-factory preflight
```

Schema enforced via JSON Schema in `src/token_factory/config/schema.py`.

## Environment variables (UI / local ops)

| Variable | Default | Purpose |
|----------|---------|---------|
| `TF_GATEWAY_URL` | `http://127.0.0.1:18080` | AI Gateway |
| `TF_SR_API_URL` | `http://127.0.0.1:8081` | SR classify API (Playground) |
| `TF_VIRTUAL_MODEL` | `token-factory/auto` | Virtual model id |
| `TF_PLAYGROUND_DIRECT_STREAM` | `1` | Classify→AIM live stream |
| `TF_MAX_TOKENS` | `4096` | Playground completion length |
| `TF_CHAT_TIMEOUT` | `300` | Chat HTTP timeout (s) |
| `HF_TOKEN` | — | SR model download secret |

See [ui.md](ui.md) for Playground streaming details.
