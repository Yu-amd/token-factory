#!/usr/bin/env bash
# Smoke-test Playground streaming path: SR classify → direct AIM SSE (live TTFT).
# Requires: port-forward to SR API (:8081) and network reachability to AIM hosts.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/lib/colors.sh"

SR_API="${TF_SR_API_URL:-${TF_SR_URL:-http://127.0.0.1:8081}}"
META="${REPO_ROOT}/generated/ui-metadata.json"
PROMPT="${1:-Write a short Python function that adds two numbers.}"

if [[ ! -f "${META}" ]]; then
  err "Missing ${META} — run: token-factory compile"
  exit 1
fi

step "Classify via Semantic Router API (${SR_API})"
CLASSIFY_JSON="$(curl -sS -m 20 -X POST "${SR_API}/api/v1/classify/intent" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json; print(json.dumps({'text': '''${PROMPT}'''}))")")"

python3 - "${META}" "${CLASSIFY_JSON}" "${PROMPT}" <<'PY'
import json, sys, time, urllib.request

meta_path, classify_raw, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
meta = json.loads(open(meta_path).read())
classify = json.loads(classify_raw)
decision = classify.get("routing_decision") or (classify.get("classification") or {}).get("category") or ""
recommended = classify.get("recommended_model") or ""
matched = next((r for r in meta.get("routes", []) if r.get("name") == decision), None)
if matched is None and recommended:
    matched = next(
        (
            r
            for r in meta.get("routes", [])
            if r.get("lora_name") == recommended
            or (r.get("endpoint") or {}).get("model") == recommended
        ),
        None,
    )
if matched is None and meta.get("routes"):
    matched = meta["routes"][-1]
if not matched:
    raise SystemExit("No route match in ui-metadata")

ep = matched["endpoint"]
model = recommended or matched.get("lora_name") or ep["model"]
url = f"http://{ep['host']}:{ep['port']}/v1/chat/completions"
print(f"route={matched.get('name')} model={model}")
print(f"aim={url}")

body = json.dumps(
    {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 64,
        "stream": True,
    }
).encode()
req = urllib.request.Request(
    url, data=body, headers={"Content-Type": "application/json"}, method="POST"
)
t0 = time.perf_counter()
first = None
chunks = 0
with urllib.request.urlopen(req, timeout=120) as resp:
    assert "text/event-stream" in (resp.headers.get("content-type") or ""), resp.headers
    buf = b""
    while True:
        piece = resp.read(256)
        if not piece:
            break
        buf += piece
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = ((obj.get("choices") or [{}])[0].get("delta") or {})
            text = delta.get("content") or delta.get("reasoning") or ""
            if text:
                if first is None:
                    first = time.perf_counter() - t0
                chunks += 1
        else:
            continue
        break

if first is None:
    raise SystemExit("No streamed tokens received from AIM")
print(f"TTFT={first:.3f}s chunks={chunks}")
if first > 5.0:
    raise SystemExit(f"TTFT too high ({first:.2f}s) — expected live AIM stream")
print("OK: classify → direct AIM live SSE")
PY

success "Playground streaming smoke passed"
