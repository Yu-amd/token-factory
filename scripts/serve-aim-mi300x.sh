#!/usr/bin/env bash
# Launch AMD AIM OpenAI-compatible servers on MI300X hosts.
# Does not hard-code credentials; pass HF_TOKEN via environment if needed.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  serve-aim-mi300x.sh --host <ssh-host> --image <aim-image> [--name <container>] [--port 8000]

Examples:
  HF_TOKEN=... ./scripts/serve-aim-mi300x.sh \
    --host root@165.245.131.224 \
    --image amdenterpriseai/aim-openai-gpt-oss-120b:0.11.1 \
    --name vllm-gpt-oss-120b

  HF_TOKEN=... ./scripts/serve-aim-mi300x.sh \
    --host root@129.212.176.75 \
    --image amdenterpriseai/aim-openai-gpt-oss-20b:0.11.1 \
    --name vllm-gpt-oss-20b

Env:
  HF_TOKEN / HUGGING_FACE_HUB_TOKEN  optional (gpt-oss does not require HF auth)
  SSH_KEY                            default ~/.ssh/eai_ed25519
  AIM_PORT                           container listen port (default 8000)
EOF
}

HOST=""
IMAGE=""
NAME=""
PORT="${AIM_PORT:-8000}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/eai_ed25519}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

[[ -n "$HOST" && -n "$IMAGE" ]] || { usage; exit 1; }
if [[ -z "$NAME" ]]; then
  NAME="aim-$(echo "$IMAGE" | sed 's|.*/||;s|:.*||')"
fi

SSH=(ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes)
[[ -f "$SSH_KEY" ]] && SSH+=(-i "$SSH_KEY")

HF_TOKEN_VAL="${HF_TOKEN:-${HUGGING_FACE_HUB_TOKEN:-}}"

"${SSH[@]}" "$HOST" bash -s -- "$IMAGE" "$NAME" "$PORT" "$HF_TOKEN_VAL" <<'REMOTE'
set -euo pipefail
IMAGE="$1"; NAME="$2"; PORT="$3"; HF_TOKEN_VAL="$4"
docker pull "$IMAGE"
docker rm -f "$NAME" 2>/dev/null || true
mkdir -p /data/aim-cache
ARGS=(
  -d --name "$NAME" --restart unless-stopped
  --device=/dev/kfd --device=/dev/dri
  --group-add video --group-add render
  --shm-size=16g
  -p "${PORT}:8000"
  -e AIM_PORT=8000
  -e AIM_ACCELERATOR_FAMILY=instinct
  -e AIM_ACCELERATOR_TYPE=gpu
  -v /data/aim-cache:/workspace/model-cache
)
if [[ -n "$HF_TOKEN_VAL" ]]; then
  ARGS+=(-e "HF_TOKEN=${HF_TOKEN_VAL}" -e "HUGGING_FACE_HUB_TOKEN=${HF_TOKEN_VAL}")
fi
docker run "${ARGS[@]}" "$IMAGE" serve
echo "started ${NAME} on :${PORT}"
docker ps --filter "name=${NAME}" --format '{{.Names}} {{.Status}} {{.Ports}}'
REMOTE

echo "Probe: curl -sS http://${HOST#*@}:${PORT}/v1/models | head"
