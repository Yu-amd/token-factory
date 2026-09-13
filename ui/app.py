"""Token Factory Streamlit UI — dark console aligned with vLLM-SR dashboard."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "generated" / "ui-metadata.json"
GATEWAY = os.environ.get("TF_GATEWAY_URL", "http://127.0.0.1:18080")
VIRTUAL_MODEL = os.environ.get("TF_VIRTUAL_MODEL", "token-factory/auto")
# Generous default so architecture / coding prompts are not truncated mid-answer.
MAX_TOKENS = int(os.environ.get("TF_MAX_TOKENS", "4096"))
CHAT_TIMEOUT = float(os.environ.get("TF_CHAT_TIMEOUT", "300"))


st.set_page_config(
    page_title="AMD Token Factory",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = textwrap.dedent(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

    :root {
      --tf-bg: #0a0a0a;
      --tf-surface: #141414;
      --tf-elevated: #1f1f1f;
      --tf-border: #333333;
      --tf-border-hover: #444444;
      --tf-text: #e8e8e8;
      --tf-muted: #999999;
      --tf-faint: #666666;
      --tf-green: #76b900;
      --tf-green-hi: #8fd400;
      --tf-green-dim: rgba(118, 185, 0, 0.12);
      --tf-danger: #ef4444;
      --tf-warn: #f59e0b;
      --tf-cyan: #00d4ff;
      --tf-max: 1400px;
    }

    html, body, [class*="css"] {
      font-family: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
    }

    .stApp {
      background:
        radial-gradient(1200px 600px at 70% -10%, rgba(118, 185, 0, 0.08), transparent 55%),
        radial-gradient(900px 500px at 10% 110%, rgba(0, 212, 255, 0.05), transparent 50%),
        var(--tf-bg) !important;
      color: var(--tf-text);
    }

    #MainMenu, footer, header { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }
    .block-container {
      max-width: var(--tf-max) !important;
      padding-top: 1.25rem !important;
      padding-bottom: 3rem !important;
    }

    .tf-chrome {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.85rem 0 1.1rem;
      border-bottom: 1px solid var(--tf-border);
      margin-bottom: 1.35rem;
    }
    .tf-brand { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
    .tf-mark {
      width: 28px; height: 28px; border-radius: 6px;
      background: linear-gradient(145deg, var(--tf-green-hi), var(--tf-green));
      box-shadow: 0 0 18px rgba(118, 185, 0, 0.35);
      display: grid; place-items: center; flex-shrink: 0;
    }
    .tf-mark svg { display: block; }
    .tf-brand-text h1 {
      margin: 0; font-size: 1.05rem; font-weight: 650;
      letter-spacing: -0.01em; color: var(--tf-text); line-height: 1.2;
    }
    .tf-brand-text p {
      margin: 0.15rem 0 0; font-size: 0.72rem; color: var(--tf-muted);
      letter-spacing: 0.04em; text-transform: uppercase;
    }
    .tf-badge {
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.35rem 0.75rem; border-radius: 999px;
      border: 1px solid var(--tf-border); background: rgba(255,255,255,0.03);
      color: var(--tf-muted); font-size: 0.75rem; font-weight: 500; white-space: nowrap;
    }
    .tf-badge strong { color: var(--tf-green-hi); font-weight: 600; }

    .tf-status-row {
      display: grid; grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 0.65rem; margin-bottom: 1.25rem;
    }
    @media (max-width: 900px) {
      .tf-status-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .tf-status {
      background: var(--tf-surface); border: 1px solid var(--tf-border);
      border-radius: 0.5rem; padding: 1rem 1.05rem;
      transition: border-color 0.15s ease;
    }
    .tf-status:hover { border-color: var(--tf-border-hover); }
    .tf-status-label {
      font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--tf-faint); margin-bottom: 0.35rem;
    }
    .tf-status-value {
      display: flex; align-items: center; gap: 0.45rem;
      font-size: 0.95rem; font-weight: 600;
      font-family: "IBM Plex Mono", ui-monospace, monospace;
    }
    .tf-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .tf-up .tf-dot { background: var(--tf-green); box-shadow: 0 0 10px rgba(118,185,0,0.55); }
    .tf-up .tf-status-value { color: var(--tf-green-hi); }
    .tf-down .tf-dot { background: var(--tf-danger); box-shadow: 0 0 10px rgba(239,68,68,0.45); }
    .tf-down .tf-status-value { color: #fca5a5; }
    .tf-warn .tf-dot { background: var(--tf-warn); }
    .tf-warn .tf-status-value { color: #fcd34d; }

    .tf-card {
      background: var(--tf-surface); border: 1px solid var(--tf-border);
      border-radius: 0.625rem; padding: 1.6rem 1.75rem; margin-bottom: 1.15rem;
    }
    .tf-card-hero {
      display: flex;
      flex-direction: column;
      gap: 0;
      padding: 2rem 2rem 1.85rem;
      margin-bottom: 1.75rem;
    }
    .tf-card-hero .tf-eyebrow {
      font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--tf-faint); margin: 0 0 1rem !important; font-weight: 500;
      line-height: 1.4;
    }
    .tf-card-hero .tf-h2 {
      margin: 0 0 1rem !important; font-size: 1.55rem; font-weight: 650;
      letter-spacing: -0.02em; color: var(--tf-text); line-height: 1.35;
    }
    .tf-card-hero .tf-sub {
      margin: 0 !important; color: var(--tf-muted); font-size: 1rem;
      line-height: 1.7; max-width: 44rem;
    }
    .tf-eyebrow {
      font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--tf-faint); margin: 0 0 0.85rem !important; font-weight: 500;
      line-height: 1.4;
    }
    .tf-h2 {
      margin: 0 0 0.85rem !important; font-size: 1.35rem; font-weight: 650;
      letter-spacing: -0.02em; color: var(--tf-text); line-height: 1.35;
    }
    .tf-sub {
      margin: 0 !important; color: var(--tf-muted); font-size: 0.95rem;
      line-height: 1.65; max-width: 52rem;
    }
    .tf-meta {
      display: flex; flex-wrap: wrap; gap: 1.25rem 2.5rem;
      margin-top: 1.5rem !important; padding-top: 1.35rem !important;
      border-top: 1px solid var(--tf-border);
    }
    .tf-meta-item {
      display: flex; flex-direction: column; gap: 0.45rem; min-width: 14rem;
    }
    .tf-meta-label {
      font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--tf-faint); font-weight: 500; line-height: 1.3;
    }
    .tf-meta-value {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.88rem; color: var(--tf-green-hi); line-height: 1.45;
    }
    .tf-mono {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.84rem;
    }

    /* Streamlit wraps st.html; neutralize collapsed spacing on wrappers */
    [data-testid="stHtml"] { margin-bottom: 0 !important; }
    [data-testid="stHtml"] > div { line-height: inherit; }

    .tf-route {
      display: grid; grid-template-columns: 1fr auto; gap: 0.5rem 1rem;
      align-items: start; padding: 1rem 1.1rem; background: var(--tf-elevated);
      border: 1px solid var(--tf-border); border-radius: 0.5rem; margin-bottom: 0.65rem;
    }
    .tf-route-name { font-weight: 600; color: var(--tf-text); font-size: 0.95rem; }
    .tf-route-model {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.78rem; color: var(--tf-cyan); margin-top: 0.2rem;
    }
    .tf-chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.55rem; }
    .tf-chip {
      font-size: 0.7rem; padding: 0.2rem 0.55rem; border-radius: 999px;
      background: var(--tf-green-dim); color: var(--tf-green-hi);
      border: 1px solid rgba(118,185,0,0.25);
    }
    .tf-hw { text-align: right; font-size: 0.75rem; color: var(--tf-muted); line-height: 1.4; }
    .tf-hw strong { color: var(--tf-text); display: block; font-size: 0.85rem; }

    .tf-flow {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 0.8rem; line-height: 1.55; color: var(--tf-muted);
      background: #0d0d0d; border: 1px solid var(--tf-border); border-radius: 0.5rem;
      padding: 1.1rem 1.25rem; overflow-x: auto; white-space: pre;
    }
    .tf-flow .hi { color: var(--tf-green-hi); }
    .tf-flow .dim { color: var(--tf-faint); }

    .tf-kv {
      display: grid; grid-template-columns: 140px 1fr; gap: 0.55rem 1rem; font-size: 0.9rem;
    }
    .tf-kv dt {
      color: var(--tf-faint); text-transform: uppercase; letter-spacing: 0.08em;
      font-size: 0.7rem; padding-top: 0.2rem;
    }
    .tf-kv dd {
      margin: 0; color: var(--tf-text);
      font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 0.85rem;
    }

    .tf-links { display: flex; flex-wrap: wrap; gap: 0.55rem; margin-top: 0.75rem; }
    .tf-link {
      display: inline-flex; align-items: center; gap: 0.4rem;
      padding: 0.55rem 0.95rem; border-radius: 999px;
      border: 1px solid var(--tf-border); background: rgba(255,255,255,0.03);
      color: var(--tf-text) !important; text-decoration: none !important;
      font-size: 0.82rem; font-weight: 500;
      transition: border-color 0.15s, background 0.15s;
    }
    .tf-link:hover {
      border-color: var(--tf-green); background: var(--tf-green-dim);
      color: var(--tf-green-hi) !important;
    }

    /* Streamlit 1.63+ tabs are div[role=tab], not baseweb buttons */
    [data-testid="stTabs"] [role="tablist"],
    div[role="tablist"] {
      display: flex !important;
      flex-wrap: wrap !important;
      align-items: center !important;
      gap: 0.85rem 1.35rem !important;
      column-gap: 1.35rem !important;
      row-gap: 0.75rem !important;
      border-bottom: 1px solid var(--tf-border) !important;
      padding: 0.15rem 0 1rem 0 !important;
      margin-bottom: 1.35rem !important;
    }
    [data-testid="stTabs"] [role="tab"],
    div[role="tablist"] [role="tab"] {
      font-family: "IBM Plex Sans", sans-serif !important;
      font-weight: 500 !important;
      font-size: 0.95rem !important;
      color: var(--tf-muted) !important;
      background: transparent !important;
      border-radius: 999px !important;
      padding: 0.55rem 1.15rem !important;
      margin: 0 !important;
      letter-spacing: 0.015em !important;
      line-height: 1.35 !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    div[role="tablist"] [role="tab"][aria-selected="true"] {
      color: var(--tf-green-hi) !important;
      background: var(--tf-green-dim) !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"] {
      display: none !important;
    }

    .stTextArea textarea, .stTextInput input,
    [data-testid="stChatInput"] textarea {
      background: var(--tf-elevated) !important;
      border: 1px solid var(--tf-border) !important;
      color: var(--tf-text) !important; border-radius: 0.5rem !important;
      font-family: "IBM Plex Sans", sans-serif !important;
    }
    .stTextArea textarea:focus, .stTextInput input:focus,
    [data-testid="stChatInput"] textarea:focus {
      border-color: var(--tf-green) !important;
      box-shadow: 0 0 0 1px rgba(118,185,0,0.35) !important;
    }

    .stButton > button {
      background: var(--tf-green) !important; color: #0a0a0a !important;
      border: none !important; border-radius: 999px !important;
      font-weight: 650 !important; letter-spacing: 0.01em;
      padding: 0.45rem 1.25rem !important;
      transition: background 0.15s, box-shadow 0.15s;
    }
    .stButton > button:hover {
      background: var(--tf-green-hi) !important;
      box-shadow: 0 0 18px rgba(118,185,0,0.35);
      color: #0a0a0a !important;
    }
    .stButton > button[kind="secondary"] {
      background: transparent !important; color: var(--tf-text) !important;
      border: 1px solid var(--tf-border) !important;
    }

    div[data-testid="stChatMessage"] {
      background: var(--tf-surface) !important; border: 1px solid var(--tf-border);
      border-radius: 0.625rem; padding: 1.15rem 1.35rem !important;
      margin-bottom: 0.85rem !important;
    }
    div[data-testid="stChatMessage"] p {
      line-height: 1.65 !important; margin-bottom: 0.75rem !important;
      font-size: 0.98rem !important;
    }
    div[data-testid="stChatMessage"] p:last-child { margin-bottom: 0 !important; }
    div[data-testid="stChatMessage"] h1,
    div[data-testid="stChatMessage"] h2,
    div[data-testid="stChatMessage"] h3 {
      margin-top: 1.1rem !important; margin-bottom: 0.55rem !important;
      line-height: 1.35 !important; letter-spacing: -0.015em;
    }
    div[data-testid="stChatMessage"] h1:first-child,
    div[data-testid="stChatMessage"] h2:first-child,
    div[data-testid="stChatMessage"] h3:first-child { margin-top: 0 !important; }
    div[data-testid="stChatMessage"] ul, div[data-testid="stChatMessage"] ol {
      margin: 0.55rem 0 0.85rem 1.1rem !important; line-height: 1.6 !important;
    }
    div[data-testid="stChatMessage"] li { margin-bottom: 0.35rem !important; }
    [data-testid="stChatInput"] {
      padding-top: 0.75rem !important; margin-top: 0.5rem !important;
    }
    [data-testid="stChatInput"] textarea {
      min-height: 3.25rem !important; line-height: 1.5 !important;
      padding: 0.85rem 1rem !important;
    }
    [data-testid="stCaptionContainer"] {
      margin-top: 0.65rem !important; line-height: 1.5 !important;
    }
    div[data-testid="stDataFrame"] {
      border: 1px solid var(--tf-border); border-radius: 0.5rem; overflow: hidden;
    }
    .stExpander {
      background: var(--tf-surface) !important; border: 1px solid var(--tf-border) !important;
      border-radius: 0.5rem !important;
    }
    .stCaption, [data-testid="stCaptionContainer"] { color: var(--tf-muted) !important; }
    </style>
    """
).strip()


def html(fragment: str) -> None:
    """Render HTML without Streamlit markdown indent/code-block traps."""
    st.html(textwrap.dedent(fragment).strip())


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


def status_class(value: str) -> str:
    if value == "UP":
        return "tf-up"
    if value.startswith("HTTP"):
        return "tf-warn"
    return "tf-down"


def render_chrome(virtual_model: str) -> None:
    html(
        f"""
        <div class="tf-chrome">
          <div class="tf-brand">
            <div class="tf-mark" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M3 11.5L8 3.5L13 11.5H3Z" fill="#0a0a0a"/>
                <path d="M5.2 10.2H10.8L8 5.8L5.2 10.2Z" fill="#76b900"/>
              </svg>
            </div>
            <div class="tf-brand-text">
              <h1>AMD Token Factory</h1>
              <p>Semantic routing · Instinct · EPYC · Radeon</p>
            </div>
          </div>
          <div class="tf-badge">Virtual model · <strong>{virtual_model}</strong></div>
        </div>
        """
    )


def render_status(checks: list[tuple[str, str]]) -> None:
    tiles = []
    for name, value in checks:
        cls = status_class(value)
        tiles.append(
            f'<div class="tf-status {cls}">'
            f'<div class="tf-status-label">{name}</div>'
            f'<div class="tf-status-value"><span class="tf-dot"></span>{value}</div>'
            f"</div>"
        )
    html(f'<div class="tf-status-row">{"".join(tiles)}</div>')


def section(
    eyebrow: str,
    title: str,
    subtitle: str,
    *,
    hero: bool = False,
    meta: list[tuple[str, str]] | None = None,
) -> None:
    card_cls = "tf-card tf-card-hero" if hero else "tf-card"
    pad = "2.35rem 2.25rem 2.1rem" if hero else "1.75rem 1.85rem"
    title_size = "1.65rem" if hero else "1.35rem"
    sub_size = "1.05rem" if hero else "0.95rem"
    eye_gap = "1.25rem" if hero else "1.05rem"
    title_gap = "1.25rem" if hero else "1.05rem"
    meta_html = ""
    if meta:
        items = "".join(
            "<div class='tf-meta-item' style='display:flex;flex-direction:column;gap:0.55rem;min-width:14rem;'>"
            f"<span class='tf-meta-label' style='font-size:0.68rem;letter-spacing:0.1em;"
            f"text-transform:uppercase;color:#666;font-weight:500;'>{label}</span>"
            f"<span class='tf-meta-value' style='font-family:IBM Plex Mono,ui-monospace,monospace;"
            f"font-size:0.9rem;color:#8fd400;line-height:1.5;'>{value}</span>"
            "</div>"
            for label, value in meta
        )
        meta_html = (
            "<div class='tf-meta' style='display:flex;flex-wrap:wrap;gap:1.5rem 3rem;"
            "margin-top:1.85rem;padding-top:1.55rem;border-top:1px solid #333;'>"
            f"{items}</div>"
        )
    html(
        f"""
        <div class="{card_cls}" style="background:#141414;border:1px solid #333;border-radius:0.625rem;
          padding:{pad};margin:0 0 1.85rem 0;">
          <p class="tf-eyebrow" style="font-size:0.72rem;letter-spacing:0.14em;text-transform:uppercase;
            color:#666;margin:0 0 {eye_gap} 0;font-weight:500;line-height:1.4;">{eyebrow}</p>
          <h2 class="tf-h2" style="margin:0 0 {title_gap} 0;font-size:{title_size};font-weight:650;
            letter-spacing:-0.02em;color:#e8e8e8;line-height:1.35;">{title}</h2>
          <p class="tf-sub" style="margin:0;color:#a3a3a3;font-size:{sub_size};line-height:1.8;
            max-width:40rem;">{subtitle}</p>
          {meta_html}
        </div>
        """
    )


def stream_chat_completion(
    prompt: str,
    model: str,
    meta: dict[str, Any],
):
    """Yield SSE text deltas from the gateway; update meta with model/finish."""
    with httpx.stream(
        "POST",
        f"{GATEWAY}/v1/chat/completions",
        headers={"Authorization": "Bearer demo-key"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "stream": True,
        },
        timeout=CHAT_TIMEOUT,
    ) as response:
        if response.status_code >= 400:
            body = response.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {response.status_code}: {body}")

        for line in response.iter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                payload = line[5:].strip()
            elif line.startswith("{"):
                payload = line.strip()
            else:
                continue
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if chunk.get("model"):
                meta["model"] = chunk["model"]
            choice = (chunk.get("choices") or [{}])[0]
            if choice.get("finish_reason"):
                meta["finish"] = choice["finish_reason"]
            delta = choice.get("delta") or {}
            # Prefer visible content; fall back to reasoning so gpt-oss streams live.
            text = delta.get("content") or delta.get("reasoning") or ""
            if text:
                if delta.get("content"):
                    meta["saw_content"] = True
                elif delta.get("reasoning"):
                    meta["saw_reasoning"] = True
                yield text


def chat_completion(prompt: str, model: str) -> dict[str, Any]:
    """Non-streaming fallback."""
    r = httpx.post(
        f"{GATEWAY}/v1/chat/completions",
        headers={"Authorization": "Bearer demo-key"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
        },
        timeout=CHAT_TIMEOUT,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    return r.json()


def extract_reply(body: dict[str, Any]) -> str:
    msg = (body.get("choices") or [{}])[0].get("message", {})
    return (msg.get("content") or msg.get("reasoning") or "").strip() or "(empty content)"


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
st.html(CSS)
meta = load_metadata()
links = meta.get("links", {})
VIRTUAL_MODEL = meta.get("virtual_model") or VIRTUAL_MODEL

if "messages" not in st.session_state:
    st.session_state.messages = []

render_chrome(VIRTUAL_MODEL)

probe_defs = [
    ("Gateway", GATEWAY, "/v1/models"),
    ("SR API", links.get("semantic_router_api", "http://localhost:8081"), "/health"),
    ("SR Dashboard", links.get("semantic_router_dashboard", "http://localhost:8700"), "/"),
    ("Grafana", links.get("grafana", "http://localhost:3000"), "/api/health"),
    ("Prometheus", links.get("prometheus", "http://localhost:9090"), "/-/healthy"),
]
render_status([(n, probe(u, p)) for n, u, p in probe_defs])

tab_chat, tab_route, tab_arch, tab_inv, tab_pol, tab_ops = st.tabs(
    ["Playground", "Routing", "Architecture", "Endpoints", "Policies", "Operations"]
)

with tab_chat:
    section(
        "Playground",
        "Chat through the gateway",
        "Send a prompt to the virtual model. Replies stream live through Envoy AI Gateway → "
        "Semantic Router → AIM backends on Instinct / EPYC / Radeon.",
        hero=True,
        meta=[
            ("Virtual model", VIRTUAL_MODEL),
            ("Gateway", GATEWAY),
        ],
    )

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("meta"):
                st.caption(msg["meta"])

    prompt = st.chat_input("Ask Token Factory… e.g. Write a ROCm kernel sketch in Python")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            stream_meta: dict[str, Any] = {
                "model": None,
                "finish": None,
                "saw_content": False,
                "saw_reasoning": False,
            }
            try:
                reply = st.write_stream(
                    stream_chat_completion(prompt, VIRTUAL_MODEL, stream_meta)
                )
                if not (reply or "").strip():
                    # Rare empty stream — fall back once without streaming.
                    body = chat_completion(prompt, VIRTUAL_MODEL)
                    reply = extract_reply(body)
                    stream_meta["model"] = body.get("model")
                    stream_meta["finish"] = (body.get("choices") or [{}])[0].get(
                        "finish_reason"
                    )
                    st.markdown(reply)
                kind = (
                    "content"
                    if stream_meta.get("saw_content")
                    else "reasoning"
                    if stream_meta.get("saw_reasoning")
                    else "stream"
                )
                meta_line = (
                    f"routed model={stream_meta.get('model') or '—'} · "
                    f"finish={stream_meta.get('finish') or '—'} · {kind} · streaming"
                )
                st.caption(meta_line)
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply, "meta": meta_line}
                )
            except Exception as exc:
                err = f"{exc} — is the gateway up? Run: `token-factory ports start`"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )

    if st.session_state.messages:
        if st.button("Clear chat", type="secondary"):
            st.session_state.messages = []
            st.rerun()

with tab_route:
    section(
        "Routing",
        "Domain → expert → AIM",
        "Compiled from policies.yaml. LoRA names are real backend model ids (AIGW route match).",
    )
    for route in meta.get("routes", []):
        ep = route.get("endpoint") or {}
        chips = "".join(
            f'<span class="tf-chip">{d}</span>' for d in route.get("domains", [])
        )
        html(
            f"""
            <div class="tf-route">
              <div>
                <div class="tf-route-name">{route.get('name', 'route')}</div>
                <div class="tf-route-model">{route.get('lora_name')} → {ep.get('model', '—')}</div>
                <div class="tf-chips">{chips}</div>
              </div>
              <div class="tf-hw">
                <strong>{(ep.get('hardware') or '—').upper()}</strong>
                {ep.get('accelerator', '')}<br/>
                {ep.get('host', '')}:{ep.get('port', '')}
              </div>
            </div>
            """
        )

with tab_arch:
    section(
        "Architecture",
        "Control path",
        'Single virtual model; Semantic Router sets <span class="tf-mono">x-ai-eg-model</span> for Envoy AI Gateway.',
    )
    html(
        """
        <div class="tf-flow"><span class="hi">Client</span>
   │  POST /v1/chat/completions  model=token-factory/auto
   ▼
<span class="hi">Envoy AI Gateway</span>  <span class="dim">(AIGW v0.4.0)</span>
   │  extproc → Semantic Router :50051
   ▼
<span class="hi">vLLM Semantic Router</span>  <span class="dim">domain classify → LoRA / x-ai-eg-model</span>
   ├─ coding / math     → openai/gpt-oss-120b  <span class="dim">Instinct MI300X</span>
   └─ general           → openai/gpt-oss-20b   <span class="dim">Instinct MI300X</span>
   ▼
<span class="hi">AIGatewayRoute</span>  <span class="dim">match header → AIServiceBackend → AIM HTTP</span></div>
        """
    )

with tab_inv:
    section(
        "Inventory",
        "Configured endpoints",
        "From endpoints.yaml after compile.",
    )
    st.dataframe(meta.get("endpoints", []), width="stretch", hide_index=True)

with tab_pol:
    section(
        "Policies",
        "Active policy pack",
        "Authoritative source under config/ and policies/.",
    )
    html(
        f"""
        <div class="tf-card">
          <dl class="tf-kv">
            <dt>Policy</dt><dd>{meta.get('policy_name', 'amd-balanced')}</dd>
            <dt>Mode</dt><dd>{meta.get('priority_mode', 'balanced')}</dd>
            <dt>Virtual model</dt><dd>{meta.get('virtual_model', VIRTUAL_MODEL)}</dd>
            <dt>Routes</dt><dd>{len(meta.get('routes', []))}</dd>
            <dt>Endpoints</dt><dd>{len(meta.get('endpoints', []))}</dd>
          </dl>
        </div>
        """
    )

with tab_ops:
    dash = links.get("semantic_router_dashboard", "http://localhost:8700")
    graf = links.get("grafana", "http://localhost:3000")
    prom = links.get("prometheus", "http://localhost:9090")
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">Operations</p>
          <h2 class="tf-h2">Sibling consoles</h2>
          <p class="tf-sub">Token Factory UI is the operator front door; deep tooling lives on these surfaces.</p>
          <div class="tf-links">
            <a class="tf-link" href="{dash}" target="_blank" rel="noopener">Semantic Router Dashboard →</a>
            <a class="tf-link" href="{graf}" target="_blank" rel="noopener">Grafana →</a>
            <a class="tf-link" href="{prom}" target="_blank" rel="noopener">Prometheus →</a>
          </div>
        </div>
        """
    )
    if st.button("Refresh metadata"):
        st.cache_data.clear()
        st.rerun()
