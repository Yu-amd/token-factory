"""Token Factory Streamlit UI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "generated" / "ui-metadata.json"
GATEWAY = os.environ.get("TF_GATEWAY_URL", "http://localhost:8080")
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
    path = "/-/healthy" if "9090" in url else "/health"
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
                json={"model": VIRTUAL_MODEL, "messages": [{"role": "user", "content": prompt}]},
                timeout=60.0,
            )
            st.json(r.json())
        except Exception as exc:
            st.error(str(exc))

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
              └─ AIServiceBackend / AIGatewayRoute (v0.3.0 CRDs)
        """,
        language="text",
    )

with tab_inv:
    st.subheader("Endpoint inventory")
    st.dataframe(meta.get("endpoints", []), use_container_width=True)

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
