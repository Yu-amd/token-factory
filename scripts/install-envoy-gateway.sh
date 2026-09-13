#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

EG_VERSION="${EG_VERSION:-v1.6.0}"
EG_VALUES="${REPO_ROOT}/deploy/manifests/ai-gateway/envoy-gateway-values.yaml"

# WHY server-side apply for CRDs:
# helm stores release state in a Secret; gateway-crds-helm exceeds the 1 MiB
# Secret size limit on many clusters. UPSTREAM: common EG install pattern /
# eai-sr-demo fallback. WHEN IT CAN BE REMOVED: when Helm supports external
# release storage or the CRD chart is split.
step "Install Gateway API + Envoy Gateway CRDs (${EG_VERSION})"
kubectl create namespace envoy-gateway-system --dry-run=client -o yaml | kubectl apply -f -
if ! helm upgrade -i eg-crds oci://docker.io/envoyproxy/gateway-crds-helm \
  --version "${EG_VERSION}" \
  --namespace envoy-gateway-system \
  --create-namespace \
  --set crds.gatewayAPI.enabled=true \
  --set crds.envoyGateway.enabled=true \
  --timeout 120s 2>/tmp/eg-crds-helm.err; then
  warn "Helm release for eg-crds failed (often Secret size limit); applying CRDs via server-side apply"
  cat /tmp/eg-crds-helm.err >&2 || true
  helm template eg-crds oci://docker.io/envoyproxy/gateway-crds-helm \
    --version "${EG_VERSION}" \
    --set crds.gatewayAPI.enabled=true \
    --set crds.envoyGateway.enabled=true \
    | kubectl apply --server-side --force-conflicts -f -
fi

kubectl get crd gateways.gateway.networking.k8s.io \
  -o go-template='Gateway API CRD present{{ "\n" }}' >/dev/null

step "Install Envoy Gateway (${EG_VERSION})"
helm upgrade -i eg oci://docker.io/envoyproxy/gateway-helm \
  --version "${EG_VERSION}" \
  --namespace envoy-gateway-system \
  --create-namespace \
  -f "${EG_VALUES}" \
  --timeout 180s

wait_deploy envoy-gateway-system envoy-gateway 180s
success "Envoy Gateway ready"
