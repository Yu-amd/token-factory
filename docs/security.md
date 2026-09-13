# Security

## Secrets

- Store `HF_TOKEN` in Kubernetes secrets; never commit tokens
- Use `.env` locally (from `.env.example`); listed in `.gitignore`

## Network

- Public demo endpoints in `endpoints.example.yaml` are for reference; restrict access in production
- Terminate TLS at Envoy Gateway for external clients

## RBAC

- Install scripts use cluster-admin equivalent via `kubectl`/`helm` — scope CI/CD service accounts minimally
- Streamlit UI runs locally by default; in-cluster deployment needs dedicated ServiceAccount

## AI Gateway v0.3.0

Pin to v0.3.0 for AIServiceBackend compatibility. v0.4+ CRD changes break generated manifests until migrated.
