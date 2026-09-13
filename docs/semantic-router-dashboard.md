# Semantic Router Dashboard

vLLM Semantic Router chart **0.3.0** ships an optional dashboard (`dashboard.enabled: true`).

## Access

| Setting | Value |
|---------|-------|
| Service port | **8700** |
| Deployment | `semantic-router-dashboard` |
| Namespace | `vllm-semantic-router-system` |

```bash
token-factory dashboard
token-factory ports start
# open http://localhost:8700
```

## Configuration

Base values: `deploy/helm/vllm-semantic-router/values.yaml`

Compiled overrides: `generated/semantic-router-values.yaml`

CI verifies Helm render includes dashboard Deployment and port 8700.

Reference: [Semantic Router PR #3752](https://github.com/vllm-project/semantic-router/pull/3752), Issue #3751.
