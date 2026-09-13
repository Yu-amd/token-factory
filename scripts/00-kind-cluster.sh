#!/usr/bin/env bash
# Bootstrap a local kind cluster for Token Factory.
#
# NOTE: Do NOT map hostPort 8080→80 — kubectl port-forward uses localhost:8080
# for the AI Gateway. Use high ports (30080/30090) for optional host ingress only.
#
# Usage: ./scripts/00-kind-cluster.sh [--name token-factory]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

CLUSTER_NAME="${CLUSTER_NAME:-token-factory}"
CNI_PLUGINS_VERSION="v1.6.2"
CNI_PLUGINS_URL="https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-amd64-${CNI_PLUGINS_VERSION}.tgz"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) CLUSTER_NAME="$2"; shift 2 ;;
    *) error "Unknown arg: $1"; exit 1 ;;
  esac
done

step "Preflight checks"
for cmd in kind kubectl docker curl; do
  command -v "${cmd}" &>/dev/null || { error "'${cmd}' not found"; exit 1; }
  success "${cmd} found"
done

step "Creating kind cluster: ${CLUSTER_NAME}"
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
  warn "Cluster '${CLUSTER_NAME}' already exists — skipping creation."
else
  cat <<EOF | kind create cluster --name "${CLUSTER_NAME}" --config -
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: ${CLUSTER_NAME}
networking:
  disableDefaultCNI: true
  podSubnet: "10.244.0.0/16"
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
      - containerPort: 30090
        hostPort: 30090
        protocol: TCP
  - role: worker
  - role: worker
kubeadmConfigPatches:
  - |
    kind: InitConfiguration
    nodeRegistration:
      kubeletExtraArgs:
        node-labels: "ingress-ready=true"
EOF
  success "Kind cluster '${CLUSTER_NAME}' created"
fi

step "Installing CNI plugins into kind nodes"
CNI_TARBALL="/tmp/cni-plugins-${CNI_PLUGINS_VERSION}.tgz"
if [[ ! -f "${CNI_TARBALL}" ]]; then
  curl -sSLo "${CNI_TARBALL}" "${CNI_PLUGINS_URL}"
fi
for node in $(kind get nodes --name "${CLUSTER_NAME}"); do
  docker cp "${CNI_TARBALL}" "${node}":/opt/cni/cni-plugins.tgz
  docker exec "${node}" tar xzf /opt/cni/cni-plugins.tgz -C /opt/cni/bin/
done

step "Installing Flannel CNI"
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
kubectl wait --for=condition=Ready nodes --all --timeout=180s

step "Cluster ready"
kubectl cluster-info --context "kind-${CLUSTER_NAME}"
success "Proceed with: bash scripts/install-all.sh"
