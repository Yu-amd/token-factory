#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

SR_CHART_VERSION="${SR_CHART_VERSION:-0.3.0}"
NS="vllm-semantic-router-system"

step "Compile configuration"
token-factory compile || python3 -m token_factory.cli.main compile

step "Install vLLM Semantic Router chart (${SR_CHART_VERSION})"
kubectl create namespace "${NS}" --dry-run=client -o yaml | kubectl apply -f -

if [[ -n "${HF_TOKEN:-}" ]]; then
  kubectl create secret generic hf-token-secret \
    --from-literal=token="${HF_TOKEN}" \
    -n "${NS}" \
    --dry-run=client -o yaml | kubectl apply -f -
else
  warn "HF_TOKEN not set — creating placeholder secret (SR may fail model download)"
  kubectl create secret generic hf-token-secret \
    --from-literal=token=placeholder \
    -n "${NS}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi

helm upgrade -i semantic-router oci://ghcr.io/vllm-project/charts/semantic-router \
  --version "${SR_CHART_VERSION}" \
  --namespace "${NS}" \
  --create-namespace \
  -f "${REPO_ROOT}/deploy/helm/vllm-semantic-router/values.yaml" \
  -f "${REPO_ROOT}/generated/semantic-router-values.yaml" \
  --timeout 600s

wait_deploy "${NS}" semantic-router 600s
kubectl get deploy -n "${NS}" semantic-router-dashboard &>/dev/null && \
  wait_deploy "${NS}" semantic-router-dashboard 180s || warn "Dashboard deployment not found yet"
success "Semantic Router ready (dashboard.enabled=true, port 8700)"
