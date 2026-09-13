#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"
source "${SCRIPT_DIR}/lib/wait.sh"

step "Install observability stack"
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-dashboard-token-factory \
  --from-file=token-factory.json="${REPO_ROOT}/observability/grafana/token-factory-dashboard.json" \
  --from-file=token-factory-automated-demo.json="${REPO_ROOT}/observability/grafana/token-factory-automated-demo.json" \
  -n observability \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${REPO_ROOT}/deploy/manifests/observability/prometheus.yaml"
kubectl apply -f "${REPO_ROOT}/deploy/manifests/observability/grafana.yaml"
wait_deploy observability prometheus 180s || warn "Prometheus not ready yet"
wait_deploy observability grafana 180s || warn "Grafana not ready yet"
success "Observability stack applied"
