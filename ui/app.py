"""Token Factory Streamlit UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "generated" / "ui-metadata.json"
GATEWAY = os.environ.get("TF_GATEWAY_URL", "http://127.0.0.1:18080")
VIRTUAL_MODEL = os.environ.get("TF_VIRTUAL_MODEL", "token-factory/auto")

st.set_page_config(page_title="AMD Token Factory", page_icon="🏭", layout="wide")


@st.cache_data(ttl=30)
def load_metadata() -> dict:
    if META_PATH.exists():
        return json.loads(META_PATH.read_text())
    return {"routes": [], "endpoints": [], "links": {}}


def probe(url: str, path: str = "/health") -> str:
    try:
        r = httpx.get(f"{url.rstrip('/')}{path}", timeout=2.5)
        return "UP" if r.status_code < 400 else f"HTTP {r.status_code}"
    except Exception:
        return "DOWN"


meta = load_metadata()
links = meta.get("links", {})
VIRTUAL_MODEL = meta.get("virtual_model") or VIRTUAL_MODEL

st.title("AMD Token Factory")
st.caption("Config-driven semantic routing reference architecture")

cols = st.columns(5)
checks = [
    ("Gateway", GATEWAY),
    ("SR API", links.get("semantic_router_api", "http://localhost:8081")),
    ("SR Dashboard", links.get("semantic_router_dashboard", "http://localhost:8700")),
    ("Grafana", links.get("grafana", "http://localhost:3000")),
    ("Prometheus", links.get("prometheus", "http://localhost:9090")),
]
for col, (name, url) in zip(cols, checks):
    if "9090" in url:
        path = "/-/healthy"
    elif "8080" in url or "18080" in url or name == "Gateway":
        path = "/v1/models"
    elif "8700" in url or "Dashboard" in name:
        path = "/"
    else:
        path = "/health"
    col.metric(name, probe(url, path))

tab_chat, tab_route, tab_arch, tab_inv, tab_pol, tab_ops = st.tabs(
    ["Chat", "Routing", "Architecture", "Endpoints", "Policies", "Operations"]
)

with tab_chat:
    st.subheader("Chat (virtual model)")
    prompt = st.text_area("Message", "Explain ROCm AIM optimized profiles on MI350X")
    if st.button("Send"):
        try:
            r = httpx.post(
                f"{GATEWAY}/v1/chat/completions",
                headers={"Authorization": "Bearer demo-key"},
                json={
                    "model": VIRTUAL_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 256,
                },
                timeout=120.0,
            )
            if r.status_code >= 400:
                st.error(f"HTTP {r.status_code}: {r.text[:500]}")
            else:
                body = r.json()
                msg = (body.get("choices") or [{}])[0].get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""
                st.write(content or "(empty content)")
                with st.expander("Raw response"):
                    st.json(body)
                st.caption(
                    f"model={body.get('model')} · gateway={GATEWAY}"
                )
        except Exception as exc:
            st.error(f"{exc} — is the gateway up? Run: token-factory ports start")

with tab_route:
    st.subheader("Routing decisions")
    for route in meta.get("routes", []):
        st.markdown(f"**{route.get('lora_name')}** → `{route.get('endpoint', {}).get('model')}`")
        st.write("Domains:", ", ".join(route.get("domains", [])))

with tab_arch:
    st.subheader("Architecture")
    st.code(
        """
Client → Envoy AI Gateway → vLLM Semantic Router (extproc)
              │                        │
              │                        ├─ coding-expert → GPT-OSS 120B (Instinct)
              │                        └─ general-expert → GPT-OSS 20B (Instinct)
              └─ AIServiceBackend / AIGatewayRoute (AIGW v0.4.0 CRDs)
        """,
        language="text",
    )

with tab_inv:
    st.subheader("Endpoint inventory")
    st.dataframe(meta.get("endpoints", []), width="stretch")

with tab_pol:
    st.subheader("Active policy")
    st.write("Policy:", meta.get("policy_name", "amd-balanced"))
    st.write("Mode:", meta.get("priority_mode", "balanced"))
    st.write("Virtual model:", meta.get("virtual_model", VIRTUAL_MODEL))

with tab_ops:
    st.subheader("Operations")
    st.markdown(
        f"- [Semantic Router Dashboard]({links.get('semantic_router_dashboard', 'http://localhost:8700')})\n"
        f"- [Grafana]({links.get('grafana', 'http://localhost:3000')})\n"
        f"- [Prometheus]({links.get('prometheus', 'http://localhost:9090')})"
    )
    if st.button("Refresh metadata"):
        st.cache_data.clear()
        st.rerun()
