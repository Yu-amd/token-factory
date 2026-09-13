#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

AIGW_VERSION="${AIGW_VERSION:-v0.4.0}"

# WHY server-side apply fallback: same Helm Secret size limit as EG CRDs.
step "Install Envoy AI Gateway CRDs (${AIGW_VERSION})"
kubectl create namespace envoy-ai-gateway-system --dry-run=client -o yaml | kubectl apply -f -
if ! helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
  --version "${AIGW_VERSION}" \
  --namespace envoy-ai-gateway-system \
  --create-namespace \
  --timeout 120s 2>/tmp/aieg-crd-helm.err; then
  warn "Helm release for aieg-crd failed; applying CRDs via server-side apply"
  cat /tmp/aieg-crd-helm.err >&2 || true
  helm template aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
    --version "${AIGW_VERSION}" \
    | kubectl apply --server-side --force-conflicts -f -
fi

step "Install Envoy AI Gateway controller (${AIGW_VERSION})"
helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm \
  --version "${AIGW_VERSION}" \
  --namespace envoy-ai-gateway-system \
  --create-namespace \
  --timeout 180s

wait_deploy envoy-ai-gateway-system ai-gateway-controller 300s
for crd in aiservicebackends.aigateway.envoyproxy.io aigatewayroutes.aigateway.envoyproxy.io; do
  kubectl wait crd/"${crd}" --for=condition=Established --timeout=60s 2>/dev/null || true
done
success "Envoy AI Gateway ready"
