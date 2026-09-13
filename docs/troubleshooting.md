# Troubleshooting

## Preflight fails

- Ensure `config/*.yaml` exist (copy from `.example.yaml`)
- Run `token-factory compile` before install

## Semantic Router not routing

- Confirm `HF_TOKEN` secret in `vllm-semantic-router-system`
- Check compiled `generated/semantic-router-values.yaml` base URLs
- Verify EnvoyPatchPolicy extproc cluster reaches SR gRPC :50051
- Confirm `global.router.auto_model_name` is `token-factory/auto` (not only `MoM`)

## Dashboard not reachable

```bash
kubectl get deploy,svc -n vllm-semantic-router-system | grep dashboard
helm get values semantic-router -n vllm-semantic-router-system | grep -A2 dashboard
```

Ensure `dashboard.enabled: true` in values.

## Port-forward conflicts

Gateway local port is **18080** (not 8080). Token Factory tracks PIDs under
`~/.cache/token-factory/runtime/` (or `.token-factory/runtime`). Use:

```bash
token-factory ports stop
token-factory ports start
```

Never `pkill kubectl` globally.

If IPv4 `localhost:8080` resets connections, an old kind cluster may still map
hostPort 8080 — recreate with `scripts/00-kind-cluster.sh` (no 8080 mapping).

## AI Gateway 404 on routes

AIGatewayRoute header values must match SR **`lora_name`** values exactly. In this
stack those are **real model IDs** (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`),
not friendly names like `coding-expert`.

Also ensure clients send `model: token-factory/auto` (SR `auto_model_name`).

## Playground slow TTFT / no live streaming

Gateway `stream: true` is often **buffered until generation completes** (TTFT ≈
full answer time). The UI defaults to **SR classify → direct AIM stream**.

Checklist:

```bash
token-factory ports start          # SR API must be on :8081
curl -s http://127.0.0.1:8081/health
bash scripts/smoke-playground-stream.sh
```

- Confirm `TF_PLAYGROUND_DIRECT_STREAM=1` (default)
- Confirm AIM hosts in `config/endpoints.yaml` are reachable from this machine
- Run `make compile` so `generated/ui-metadata.json` has routes
- Caption should show `live AIM · route=…`; `gateway-buffered` means fallback path

## Grafana panels empty

Prometheus needs RBAC + Envoy `/stats/prometheus:19001` scrape. Re-apply:

```bash
bash scripts/install-observability.sh
```

See [observability.md](observability.md).
