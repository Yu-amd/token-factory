#!/usr/bin/env bash
# Token Factory full stack installer (modular, idempotent)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"

USE_MOCK_BACKENDS=false
SKIP_OBSERVABILITY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mock-backends) USE_MOCK_BACKENDS=true; shift ;;
    --skip-observability) SKIP_OBSERVABILITY=true; shift ;;
    *) error "Unknown arg: $1"; exit 1 ;;
  esac
done

for cmd in helm kubectl; do
  command -v "${cmd}" &>/dev/null || { error "'${cmd}' not found"; exit 1; }
done

step "Token Factory install — pinned versions"
info "Semantic Router chart: 0.3.0 | AIGW: v0.4.0 | EG: v1.6.0"

"${SCRIPT_DIR}/install-envoy-gateway.sh"
"${SCRIPT_DIR}/install-envoy-ai-gateway.sh"
token-factory compile 2>/dev/null || python3 -m token_factory.cli.main compile
"${SCRIPT_DIR}/install-semantic-router.sh"
"${SCRIPT_DIR}/apply-generated.sh"

if [[ "${USE_MOCK_BACKENDS}" == "true" ]]; then
  step "Deploy mock OpenAI-compatible backends"
  kubectl create configmap mock-backend-server \
    --from-file=server.py="${REPO_ROOT}/tests/mock_backends/server.py" \
    -n token-factory \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -f "${REPO_ROOT}/tests/mock_backends/manifests.yaml"
fi

if [[ "${SKIP_OBSERVABILITY}" != "true" ]]; then
  "${SCRIPT_DIR}/install-observability.sh"
fi

step "Installation complete"
info "Next: make ports  # gateway :18080, SR API :8081, dashboard :8700"
info "Then:  make ui    # Playground live AIM stream on :8501"
info "Smoke: make smoke-ui"
