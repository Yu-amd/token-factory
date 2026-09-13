# eai-sr-demo Parity

Reference demo: `/tmp/eai-sr-demo` (functional lessons only; **not** copied structure).

## Adopted patterns

| Pattern | Token Factory implementation |
|---------|------------------------------|
| AIGW v0.4.0 + EG v1.6.0 | Pinned in install scripts (e2e-tested combo) |
| SR extproc EnvoyPatchPolicy + Cluster | Compiler emits full eai-style patch |
| ClientTrafficPolicy 32Mi buffer | Compiler-generated |
| `x-ai-eg-model` routing | AIGatewayRoute; **lora_name = real model IDs** (AIGW override gap) |
| Dashboard port 8700 | `dashboard.enabled: true`; `token-factory dashboard` |
| Modular bash installers | `scripts/00-kind-cluster.sh`, `install-*.sh` |
| BackendTrafficPolicy health | Compiler-generated `/v1/models` + retry |

## Intentional differences

| eai-sr-demo | Token Factory |
|-------------|---------------|
| Hard-coded manifests | Config compiler → `generated/` |
| `MoM` virtual model (SR default) | `token-factory/auto` via `global.router.auto_model_name` |
| `default` namespace | `token-factory` namespace |
| Latest Helm tags | Pinned SR 0.3.0 / AIGW v0.4.0 / EG v1.6.0 |
| pkill/lsof port cleanup | PID-tracked port-forward manager |
| Manual SR ConfigMap sed | Compiler owns SR Helm values |
| Uses 165.245.133.102 demo | Clean kind + public MI300X IPs only |
| LoRA names (coding-expert) | Real model IDs for dual extproc |

## V1 verified beyond eai-sr-demo

- Real MI300X routing to 129.212.183.201 / 165.245.136.245
- SR dashboard HTTP 200 via `token-factory dashboard`
- gateway-crds server-side apply workaround documented
- SR Service selector patch for chart 0.3.0 dashboard collision
- Playground live TTFT via SR classify → direct AIM stream (`docs/ui.md`)

## Not ported

- Remote SSH tunnel scripts (`03-tunnel.sh`)
- In-cluster Streamlit deployment (local `make ui` instead)
- kind hostPort 8080 mapping (conflicts with port-forward)
