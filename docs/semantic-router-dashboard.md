# Semantic Router Dashboard

vLLM Semantic Router chart **0.3.0** ships an optional dashboard (`dashboard.enabled: true`).

## Verified resources (kind cluster `token-factory`)

| Field | Value |
|-------|-------|
| **Enabled** | `true` in `deploy/helm/vllm-semantic-router/values.yaml` |
| **Deployment** | `semantic-router-dashboard` |
| **Service** | `semantic-router-dashboard` |
| **Namespace** | `vllm-semantic-router-system` |
| **Port** | **8700/TCP** (Service `port` and `targetPort`) |
| **Image tag** | `v0.3.0` (pinned; chart default is `latest`) |

## Access

### Recommended: `token-factory dashboard`

```bash
token-factory dashboard
```

This command:

1. Discovers the dashboard Service name in `vllm-semantic-router-system` (prefers names containing `dashboard`)
2. Checks `semantic-router-dashboard` Deployment readiness
3. Picks local port 8700 (or 8701–8703 if occupied)
4. Starts a **tracked** port-forward (PID stored under `.token-factory/runtime/` or `~/.cache/token-factory/`)
5. Verifies HTTP with `curl -f http://localhost:PORT/`
6. Prints a status panel with service, deployment, URL, and probe result

### Alternative: all port-forwards

```bash
token-factory ports start
# open http://localhost:8700
```

## Post-install workaround (chart 0.3.0)

Chart 0.3.0 dashboard pods can share Service `selectorLabels` with the router, causing gRPC :50051 to intermittently hit dashboard pods. `scripts/install-semantic-router.sh` patches:

- Deployment `semantic-router` → label `token-factory.amd.com/role=router`
- Service `semantic-router` → selector includes that label

**Upstream:** [Issue #3751](https://github.com/vllm-project/semantic-router/issues/3751), [PR #3752](https://github.com/vllm-project/semantic-router/pull/3752) (commit 291c084).

## Upstream CLI caveat

Native CLI: `vllm-sr dashboard --target k8s` expects ClusterIP reachability from the operator machine. On kind, use **`kubectl port-forward`** (what `token-factory dashboard` automates) rather than assuming in-cluster DNS from the host.

## Configuration files

| File | Purpose |
|------|---------|
| `deploy/helm/vllm-semantic-router/values.yaml` | Base chart overrides (`dashboard.enabled: true`) |
| `generated/semantic-router-values.yaml` | Compiled routing config from `token-factory compile` |

CI verifies Helm template includes dashboard Deployment/Service on port 8700.

## Health probing

- **`token-factory status`** probes dashboard at **`/`** (not `/health`)
- **`token-factory dashboard`** requires HTTP 200 on `/` before reporting success
