# Troubleshooting

## Preflight fails

- Ensure `config/*.yaml` exist (copy from `.example.yaml`)
- Run `token-factory compile` before install

## Semantic Router not routing

- Confirm `HF_TOKEN` secret in `vllm-semantic-router-system`
- Check compiled `generated/semantic-router-values.yaml` base URLs
- Verify EnvoyPatchPolicy extproc cluster reaches SR gRPC :50051

## Dashboard not reachable

```bash
kubectl get deploy,svc -n vllm-semantic-router-system | grep dashboard
helm get values semantic-router -n vllm-semantic-router-system | grep -A2 dashboard
```

Ensure `dashboard.enabled: true` in values.

## Port-forward conflicts

Token Factory tracks PIDs under `~/.cache/token-factory/runtime/` (or `.token-factory/runtime`). Use:

```bash
token-factory ports stop
token-factory ports start
```

Never `pkill kubectl` globally.

## AI Gateway 404 on routes

AIGatewayRoute header values must match SR LoRA names exactly (`coding-expert`, `general-expert`, …).
