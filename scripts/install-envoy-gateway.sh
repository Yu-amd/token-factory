#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

EG_VERSION="${EG_VERSION:-v1.2.3}"
EG_VALUES="${REPO_ROOT}/deploy/manifests/ai-gateway/envoy-gateway-values.yaml"

step "Install Gateway API + Envoy Gateway CRDs (${EG_VERSION})"
helm upgrade -i eg-crds oci://docker.io/envoyproxy/gateway-crds-helm \
  --version "${EG_VERSION}" \
  --namespace envoy-gateway-system \
  --create-namespace \
  --set crds.gatewayAPI.enabled=true \
  --set crds.envoyGateway.enabled=true \
  --timeout 120s

step "Install Envoy Gateway (${EG_VERSION})"
helm upgrade -i eg oci://docker.io/envoyproxy/gateway-helm \
  --version "${EG_VERSION}" \
  --namespace envoy-gateway-system \
  --create-namespace \
  -f "${EG_VALUES}" \
  --timeout 180s

wait_deploy envoy-gateway-system envoy-gateway 180s
success "Envoy Gateway ready"
