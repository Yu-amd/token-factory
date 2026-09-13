#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"

step "Uninstall Token Factory stack"
helm uninstall semantic-router -n vllm-semantic-router-system --ignore-not-found 2>/dev/null || true
helm uninstall aieg -n envoy-ai-gateway-system --ignore-not-found 2>/dev/null || true
helm uninstall aieg-crd -n envoy-ai-gateway-system --ignore-not-found 2>/dev/null || true
helm uninstall eg -n envoy-gateway-system --ignore-not-found 2>/dev/null || true
helm uninstall eg-crds -n envoy-gateway-system --ignore-not-found 2>/dev/null || true
kubectl delete -f "${REPO_ROOT}/generated/ai-gateway-manifests.yaml" --ignore-not-found 2>/dev/null || true
kubectl delete -f "${REPO_ROOT}/deploy/manifests/observability/" --ignore-not-found 2>/dev/null || true
kubectl delete -f "${REPO_ROOT}/tests/mock_backends/manifests.yaml" --ignore-not-found 2>/dev/null || true
success "Uninstall complete (namespaces retained for safety)"
