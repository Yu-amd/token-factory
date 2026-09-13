# eai-sr-demo Parity

Reference demo: `/tmp/eai-sr-demo` (functional lessons only).

## Adopted patterns

| Pattern | Token Factory implementation |
|---------|------------------------------|
| AIGW v0.4.0 CRDs | `generated/ai-gateway-manifests.yaml` |
| SR extproc EnvoyPatchPolicy | Compiler emits patch policy |
| `x-ai-eg-model` header routing | AIGatewayRoute rules per LoRA |
| Dashboard port 8700 | `dashboard.enabled: true` in Helm values |
| Modular bash installers | `scripts/install-*.sh` |

## Intentional differences

| eai-sr-demo | Token Factory |
|-------------|---------------|
| Hard-coded manifests | Config compiler from YAML |
| `MoM` virtual model | `token-factory/auto` |
| `default` namespace | `token-factory` namespace |
| Latest Helm tags | Pinned SR 0.3.0 / AIGW v0.4.0 / EG v1.6.0 |
| pkill/lsof port cleanup | PID-tracked port-forward manager |
| Single demo values file | policies/ profiles + AIM catalog |

## Not ported

- Remote SSH tunnel scripts (parent handles access)
- In-cluster Streamlit deployment (local `make ui` instead)
- Manual SR ConfigMap sed patches (compiler owns config)
