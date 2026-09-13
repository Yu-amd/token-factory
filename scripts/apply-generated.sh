#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"

step "Apply generated AI Gateway manifests"
kubectl create namespace token-factory --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${REPO_ROOT}/generated/ai-gateway-manifests.yaml"
success "Generated manifests applied"
