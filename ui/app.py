"""Token Factory Streamlit UI — dark console aligned with vLLM-SR dashboard."""

from __future__ import annotations

import json
import os
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Iterator

import httpx
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
META_PATH = ROOT / "generated" / "ui-metadata.json"
GATEWAY = os.environ.get("TF_GATEWAY_URL", "http://127.0.0.1:18080")
SR_API = os.environ.get("TF_SR_API_URL") or os.environ.get(
    "TF_SR_URL", "http://127.0.0.1:8081"
)
VIRTUAL_MODEL = os.environ.get("TF_VIRTUAL_MODEL", "token-factory/auto")
# Generous default so architecture / coding prompts are not truncated mid-answer.
MAX_TOKENS = int(os.environ.get("TF_MAX_TOKENS", "4096"))
CHAT_TIMEOUT = float(os.environ.get("TF_CHAT_TIMEOUT", "300"))
# WHY: AIGW buffers SSE until complete (TTFT ≈ full generation). Playground
# classifies via SR API then streams directly from the AIM endpoint for live TTFT.
# Set TF_PLAYGROUND_DIRECT_STREAM=0 to force gateway path.
DIRECT_STREAM = os.environ.get("TF_PLAYGROUND_DIRECT_STREAM", "1").lower() not in (
    "0",
    "false",
    "no",
)


st.set_page_config(
    page_title="AMD Token Factory",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Expose Automated Demo Prometheus counters when a Streamlit session runs.
# A long-lived file-backed server is also started by `make ui` on :9108.
try:
    _src = str(ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, _src)
    from token_factory.demo.metrics_server import start_metrics_server

    start_metrics_server()
except Exception:  # noqa: BLE001 — UI must boot even if metrics port is busy
    pass

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
      padding-top: 0.75rem !important;
      padding-bottom: 1.25rem !important;
    }

    .tf-chrome {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 0.45rem 0 0.65rem;
      border-bottom: 1px solid var(--tf-border);
      margin-bottom: 0.75rem;
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
      gap: 0.55rem 1.0rem !important;
      column-gap: 1.0rem !important;
      row-gap: 0.5rem !important;
      border-bottom: 1px solid var(--tf-border) !important;
      padding: 0.1rem 0 0.65rem 0 !important;
      margin-bottom: 0.75rem !important;
    }
    [data-testid="stTabs"] [role="tab"],
    div[role="tablist"] [role="tab"] {
      font-family: "IBM Plex Sans", sans-serif !important;
      font-weight: 500 !important;
      font-size: 0.88rem !important;
      color: var(--tf-muted) !important;
      background: transparent !important;
      border-radius: 999px !important;
      padding: 0.4rem 0.95rem !important;
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


def classify_intent(prompt: str, sr_api: str) -> dict[str, Any]:
    """Call Semantic Router classification API (~100ms)."""
    r = httpx.post(
        f"{sr_api.rstrip('/')}/api/v1/classify/intent",
        json={"text": prompt},
        timeout=15.0,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"classify HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def resolve_aim_target(
    ui_meta: dict[str, Any], classify: dict[str, Any]
) -> tuple[str, str, str]:
    """Map classify result → (chat_url, model_id, route_name)."""
    decision = (
        classify.get("routing_decision")
        or (classify.get("classification") or {}).get("category")
        or ""
    )
    recommended = classify.get("recommended_model") or ""
    routes = ui_meta.get("routes") or []

    matched = None
    for route in routes:
        if route.get("name") == decision:
            matched = route
            break
    if matched is None and recommended:
        for route in routes:
            ep = route.get("endpoint") or {}
            if route.get("lora_name") == recommended or ep.get("model") == recommended:
                matched = route
                break
    if matched is None and routes:
        matched = routes[-1]

    if not matched:
        raise RuntimeError("No routes in ui-metadata to resolve AIM target")

    ep = matched.get("endpoint") or {}
    host = ep.get("host")
    port = ep.get("port", 8000)
    model_id = recommended or matched.get("lora_name") or ep.get("model")
    if not host or not model_id:
        raise RuntimeError(f"Incomplete endpoint for route {matched.get('name')}")
    url = f"http://{host}:{port}/v1/chat/completions"
    return url, str(model_id), str(matched.get("name") or decision or "route")


def _iter_sse_text(response: httpx.Response, meta: dict[str, Any]) -> Iterator[str]:
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
        text = delta.get("content") or delta.get("reasoning") or ""
        if not text:
            continue
        if delta.get("content"):
            meta["saw_content"] = True
        elif delta.get("reasoning"):
            meta["saw_reasoning"] = True
        yield text


def stream_from_aim(
    prompt: str,
    chat_url: str,
    model_id: str,
    meta: dict[str, Any],
) -> Iterator[str]:
    """True progressive SSE from an OpenAI-compatible AIM endpoint."""
    meta["stream_path"] = "direct-aim"
    with httpx.stream(
        "POST",
        chat_url,
        json={
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAX_TOKENS,
            "stream": True,
        },
        timeout=CHAT_TIMEOUT,
    ) as response:
        if response.status_code >= 400:
            body = response.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"AIM HTTP {response.status_code}: {body}")
        yield from _iter_sse_text(response, meta)


def stream_via_gateway(
    prompt: str,
    model: str,
    meta: dict[str, Any],
) -> Iterator[str]:
    """Gateway path — often buffered until generation completes (slow TTFT)."""
    meta["stream_path"] = "gateway"
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

        last_arrive = time.perf_counter()
        for text in _iter_sse_text(response, meta):
            now = time.perf_counter()
            gap = now - last_arrive
            last_arrive = now
            if gap < 0.005:
                meta["gateway_buffered"] = True
                time.sleep(min(0.028, 0.008 + len(text) * 0.003))
            yield text


def stream_chat_completion(
    prompt: str,
    model: str,
    meta: dict[str, Any],
    ui_meta: dict[str, Any],
    sr_api: str,
    on_event: Any | None = None,
) -> Iterator[str]:
    """Prefer SR classify → direct AIM stream (live TTFT); fall back to gateway.

    Optional ``on_event(name, payload)`` fires at real request stages (no fake timers):
    classifying | classified | streaming | fallback.
    """

    def _emit(name: str, payload: dict[str, Any] | None = None) -> None:
        if on_event is None:
            return
        try:
            on_event(name, payload or {})
        except Exception:
            pass

    if DIRECT_STREAM:
        try:
            _emit("classifying", {})
            t0 = time.perf_counter()
            classified = classify_intent(prompt, sr_api)
            chat_url, model_id, route = resolve_aim_target(ui_meta, classified)
            meta["route"] = route
            meta["classify_ms"] = int((time.perf_counter() - t0) * 1000)
            meta["aim_url"] = chat_url
            conf = (classified.get("classification") or {}).get("confidence")
            if conf is not None:
                meta["confidence"] = conf
            meta["classified"] = classified
            _emit(
                "classified",
                {
                    "classified": classified,
                    "route": route,
                    "model_id": model_id,
                    "aim_url": chat_url,
                    "classify_ms": meta["classify_ms"],
                    "confidence": conf,
                },
            )
            meta["stream_path"] = "direct-aim"
            _emit("streaming", {"stream_path": "direct-aim"})
            yield from stream_from_aim(prompt, chat_url, model_id, meta)
            return
        except Exception as exc:
            meta["direct_error"] = str(exc)[:200]
            _emit("fallback", {"reason": meta["direct_error"]})
    meta["stream_path"] = "gateway"
    _emit("streaming", {"stream_path": "gateway"})
    yield from stream_via_gateway(prompt, model, meta)


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
# Bulky global status tiles removed — Playground owns the compact health strip.
# Other tabs keep normal page scroll; Playground uses fixed-height scroll regions.

tab_chat, tab_demo, tab_matrix, tab_route, tab_arch, tab_inv, tab_pol, tab_ops = st.tabs(
    [
        "Playground",
        "Automated Demo",
        "AMD Routing Matrix",
        "Routing",
        "Architecture",
        "Endpoints",
        "Policies",
        "Operations",
    ]
)

with tab_chat:
    from views.playground import render_playground_tab

    sr_api = links.get("semantic_router_api") or SR_API
    render_playground_tab(
        meta=meta,
        links=links,
        virtual_model=VIRTUAL_MODEL,
        sr_api=sr_api,
        direct_stream=DIRECT_STREAM,
        probe_defs=probe_defs,
        probe=probe,
        stream_chat_completion=stream_chat_completion,
        chat_completion=chat_completion,
        extract_reply=extract_reply,
        html=html,
    )

with tab_demo:
    from views.automated_demo import render_automated_demo_tab

    render_automated_demo_tab(meta=meta, links=links, html=html, section=section)

# ---------------------------------------------------------------------------
# AMD Opinionated Routing Matrix
# ---------------------------------------------------------------------------
with tab_matrix:
    import sys

    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from token_factory.routing_matrix import RecommendationEngine

    try:
        engine = RecommendationEngine()
        uc_opts = {u["display_name"]: u["id"] for u in engine.list_use_cases()}
        obj_opts = {o["display_name"]: o["id"] for o in engine.list_objectives()}
        life_opts = {m["display_name"]: m["id"] for m in engine.list_lifecycle_modes()}
        serve_opts = {
            s["display_name"]: s["id"] for s in engine.list_serving_patterns()
        }
        # Prefer objective aliased from active V1 policy profile when present
        active_mode = meta.get("priority_mode") or (meta.get("routing_matrix") or {}).get(
            "priority_mode"
        )
        default_obj_id = (
            engine.resolve_objective(active_mode, "coding-assistant")
            if active_mode
            else "balanced"
        )
        obj_ids = [o["id"] for o in engine.list_objectives()]
        default_obj_idx = obj_ids.index(default_obj_id) if default_obj_id in obj_ids else 0
        dep_opts = {
            "Any": None,
            "Enterprise / Datacenter": "enterprise",
            "Workstation / Local": "workstation",
            "Edge / Local": "edge",
        }
        show_opts = {
            "All AIMs": "all",
            "Suitable": "suitable",
            "Recommended": "recommended",
            "Deployed": "deployed",
            "Preview / Tech Preview": "preview-tp",
            "Recommended + Supported": "suitable",
        }
        view_opts = {
            "Portfolio Matrix (full catalog)": "portfolio",
            "Executive View (truncated)": "executive",
        }
        compute_group_opts = {
            "All compute": "all",
            "Instinct": "instinct",
            "EPYC": "epyc",
            "Radeon": "radeon",
        }

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            uc_names = list(uc_opts.keys())
            default_uc = "Coding Assistant"
            uc_idx = uc_names.index(default_uc) if default_uc in uc_names else 0
            uc_label = st.selectbox("Use Case", uc_names, index=uc_idx)
        with c2:
            obj_label = st.selectbox("Objective", list(obj_opts.keys()), index=default_obj_idx)
        with c3:
            dep_label = st.selectbox("Deployment", list(dep_opts.keys()), index=1)
        with c4:
            life_label = st.selectbox(
                "Lifecycle",
                list(life_opts.keys()),
                index=list(life_opts.values()).index("production")
                if "production" in life_opts.values()
                else 0,
            )
        with c5:
            view_label = st.selectbox("View", list(view_opts.keys()), index=0)

        c6, c7, c8, c9 = st.columns(4)
        with c6:
            show_label = st.selectbox("Show", list(show_opts.keys()), index=0)
        with c7:
            serve_label = st.selectbox(
                "Serving Pattern",
                list(serve_opts.keys()),
                index=list(serve_opts.values()).index("interactive")
                if "interactive" in serve_opts.values()
                else 0,
                help="Interactive ≠ high traffic. Batch ≠ high-concurrency interactive.",
            )
        with c8:
            util = st.select_slider(
                "Traffic / utilization",
                options=["low", "medium", "high"],
                value="medium",
                help="Traffic is independent of serving pattern and materially affects scores.",
            )
        with c9:
            compute_group_label = st.selectbox(
                "Compute columns",
                list(compute_group_opts.keys()),
                index=0,
                help="Full compute catalog by default. Focus columns are ordering/Executive only.",
            )

        f1, f2, f3 = st.columns(3)
        with f1:
            search_q = st.text_input("Search models", value="", placeholder="e.g. Qwen, Llama, gemma")
        with f2:
            vendor_filter = st.text_input(
                "Vendor filter",
                value="",
                placeholder="e.g. Qwen, meta-llama, google",
            )
        with f3:
            data_loc = st.checkbox(
                "Data locality / privacy (prefer local Radeon)",
                value=False,
            )
        compute_focus = st.selectbox(
            "I have compute… (optional invert)",
            ["—"] + [c["id"] for c in engine.list_compute()],
            help="Why EPYC: CPU-centric/batch/fleet — not a GPU interactive competitor. "
            "Why Radeon: local/workstation/privacy when capable. "
            "Why MI350P: PCIe enterprise between workstation and rack Instinct (Tech Preview).",
        )

        endpoints = meta.get("endpoints") or []
        life_mode = life_opts[life_label]
        serve_pattern = serve_opts[serve_label]

        if compute_focus != "—":
            inv = engine.recommend_for_compute(
                compute_focus,
                objective=obj_opts[obj_label],
                endpoints=endpoints,
                lifecycle_mode=life_mode,
                use_case_id=uc_opts[uc_label],
            )
            st.markdown(f"### Recommended AIMs for `{compute_focus}`")
            tip = {
                "EPYC_9965": "Why EPYC: CPU-centric / batch / low-QPS / fleet utilization — "
                "NOT a GPU interactive competitor. Rises for batch/offline + relaxed latency.",
                "EPYC_ZEN4": "Why EPYC: CPU-centric / batch / fleet utilization — not for "
                "high-concurrency interactive.",
                "EPYC_ZEN5": "Why EPYC: CPU-centric / batch / fleet utilization — not for "
                "high-concurrency interactive.",
                "R9700": "Why Radeon: local / workstation / privacy. Can win when capable + "
                "locality preferred; never when incapable (e.g. text-only for VLM).",
                "W7900": "Why Radeon: local / workstation / privacy when AIM is capable.",
                "MI350P": "Why MI350P: PCIe enterprise Instinct between workstation and rack; "
                "Tech Preview AIMs via private eval — never silent production GA.",
            }.get(compute_focus)
            if tip:
                st.caption(tip)
            st.caption(f"Lifecycle mode: {inv.get('lifecycle_mode')} · Escalation: {inv.get('escalation_hint')}")
            for block in inv["use_cases"][:8]:
                st.markdown(f"**{block['use_case']['display_name']}**")
                for row in block["top"]:
                    live = " ● Live" if row.get("endpoint_available") else ""
                    life = row.get("lifecycle", "")
                    st.caption(
                        f"#{row.get('rank') or '—'} {row['model']} · {row['recommendation']} · "
                        f"AIM {row['aim_support']} · {life}{live}"
                    )
        else:
            matrix = engine.matrix(
                uc_opts[uc_label],
                objective=obj_opts[obj_label],
                deployment=dep_opts[dep_label],
                utilization=util,
                endpoints=endpoints,
                show=show_opts[show_label],
                lifecycle_mode=life_mode,
                data_locality=data_loc,
                serving_pattern=serve_pattern,
                view_mode=view_opts[view_label],
                search=search_q or None,
                vendor=vendor_filter or None,
                compute_group=compute_group_opts[compute_group_label],
            )
            ranked = matrix.get("ranked") or []
            cards = matrix.get("summary_cards") or {}

            # Summary cards (distinct selectors)
            card_keys = [
                k
                for k in (
                    "best_performance",
                    "best_balance",
                    "lowest_cost_sufficient",
                    "best_batch",
                    "best_local",
                )
                if k in cards
            ]
            card_html_parts = []
            for key in card_keys:
                card = cards.get(key) or {}
                cand = card.get("candidate") or {}
                label = card.get("label") or key
                if cand:
                    body = (
                        f"<div style='color:#e8e8e8;font-family:IBM Plex Mono,monospace;font-size:0.82rem;'>"
                        f"{cand.get('model','—')}</div>"
                        f"<div style='color:#999;font-size:0.78rem;margin-top:0.25rem;'>"
                        f"{cand.get('compute','')} · {cand.get('lifecycle','')} · "
                        f"{cand.get('preference_label') or cand.get('recommendation','')}</div>"
                        f"<div style='color:#666;font-size:0.72rem;margin-top:0.35rem;'>"
                        f"Infra {cand.get('infrastructure_cost_class') or cand.get('hardware_cost_class','—')} · "
                        f"Token econ fit {cand.get('token_economic_fit', cand.get('economic_fit','—'))} · "
                        f"Evidence {cand.get('cost_evidence','RELATIVE')}</div>"
                    )
                    if key == "best_balance" and card.get("why_not_performance"):
                        why = card["why_not_performance"][0]
                        body += (
                            f"<div style='color:#8a8a6a;font-size:0.7rem;margin-top:0.4rem;line-height:1.35;'>"
                            f"{why}</div>"
                        )
                else:
                    body = "<div style='color:#666;'>No eligible candidate</div>"
                card_html_parts.append(
                    f"<div style='flex:1;min-width:180px;background:#141414;border:1px solid #333;"
                    f"border-radius:0.5rem;padding:1rem;'>"
                    f"<div style='color:#666;font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;'>"
                    f"{label}</div>{body}</div>"
                )
            html(
                f"<div style='display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1rem;'>"
                f"{''.join(card_html_parts)}</div>"
            )

            if matrix.get("locality_note"):
                st.warning(matrix["locality_note"])

            # Executive card — labels come from engine ranks
            if ranked:
                top = ranked[0]
                alt = ranked[1] if len(ranked) > 1 else None
                fb = ranked[2] if len(ranked) > 2 else None
                top_level = top.get("recommendation") or "RANKED"
                pref = top.get("preference_label") or ""
                html(
                    f"""
                    <div class="tf-card" style="background:#141414;border:1px solid #333;border-radius:0.625rem;padding:1.5rem;margin-bottom:1rem;">
                      <p class="tf-eyebrow" style="color:#666;letter-spacing:0.12em;text-transform:uppercase;font-size:0.72rem;">Use-case recommendation · {pref}</p>
                      <h2 style="margin:0.4rem 0 0.8rem;color:#e8e8e8;font-size:1.35rem;">{matrix['use_case']['display_name']}</h2>
                      <p style="color:#8fd400;margin:0 0 0.35rem;font-weight:600;">{top_level} · Rank #{top.get('rank')}</p>
                      <p style="color:#e8e8e8;margin:0;font-family:IBM Plex Mono,monospace;font-size:0.95rem;">{top['model']}</p>
                      <p style="color:#999;margin:0.25rem 0 0.75rem;">{top['compute']} · AIM {top['aim_support']} · {top.get('lifecycle','')} · {top['recommendation']}{' · ● Live' if top.get('endpoint_available') else ''}</p>
                      <p style="color:#666;font-size:0.85rem;line-height:1.5;">{' · '.join(top.get('reasons', [])[:4])}</p>
                      <div style="display:flex;gap:2rem;margin-top:1rem;flex-wrap:wrap;">
                        <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;">Alternative</div>
                          <div style="color:#e8e8e8;font-family:IBM Plex Mono,monospace;font-size:0.82rem;">{(alt or {}).get('model','—')}<br/>{(alt or {}).get('compute','')}</div></div>
                        <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;">Fallback</div>
                          <div style="color:#e8e8e8;font-family:IBM Plex Mono,monospace;font-size:0.82rem;">{(fb or {}).get('model','—')}<br/>{(fb or {}).get('compute','')}</div></div>
                        <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.1em;text-transform:uppercase;">Economic Fit for Workload</div>
                          <div style="color:#e8e8e8;font-size:0.82rem;">Infrastructure Cost Class: {top.get('infrastructure_cost_class') or top.get('hardware_cost_class','—')}<br/>
                          Token Economic Fit: {top.get('token_economic_fit', top.get('economic_fit','—'))}<br/>
                          Cost Evidence: {top.get('cost_evidence','RELATIVE')}<br/><span style="color:#666;">No fabricated $/token</span></div></div>
                      </div>
                    </div>
                    """
                )

            # Matrix columns: full compute catalog (group toggle); Executive uses focus ordering.
            view_mode = matrix.get("view_mode") or "portfolio"
            if view_mode == "executive":
                focus_col_ids = tuple(matrix.get("focus_columns") or [])
                if not focus_col_ids:
                    focus_col_ids = (
                        "MI300X",
                        "MI325X",
                        "MI350P",
                        "MI350X",
                        "MI355X",
                        "EPYC_9965",
                        "R9700",
                        "W7900",
                    )
                display_cols = [c for c in matrix["columns"] if c in focus_col_ids]
                for required in ("MI350P", "R9700", "W7900"):
                    if required not in display_cols and required in (matrix.get("columns_all") or matrix.get("columns") or []):
                        display_cols.append(required)
            else:
                display_cols = list(matrix.get("columns") or [])

            row_models = list(matrix.get("display_rows") or [])
            if not row_models:
                row_models = list(matrix.get("rows") or [])

            row_status = matrix.get("row_status") or {}
            why_not = matrix.get("why_not_recommended") or {}
            cc = matrix.get("catalog_counts") or {}
            catalog_n = cc.get("catalog_models") or len(matrix.get("rows") or [])
            shown_n = len(row_models)
            strip = (
                f"<div style='display:flex;flex-wrap:wrap;gap:0.75rem 1.25rem;margin:0.35rem 0 0.75rem;"
                f"padding:0.65rem 0.85rem;background:#121212;border:1px solid #2e2e2e;border-radius:0.45rem;"
                f"font-size:0.78rem;color:#bbb;'>"
                f"<span><b style='color:#e8e8e8;'>{shown_n}/{catalog_n}</b> catalog</span>"
                f"<span>suitable <b style='color:#e8e8e8;'>{cc.get('suitable', 0)}</b></span>"
                f"<span>recommended <b style='color:#8fd400;'>{cc.get('recommended', 0)}</b></span>"
                f"<span>deployed <b style='color:#e8e8e8;'>{cc.get('deployed', 0)}</b></span>"
                f"<span>preview/TP <b style='color:#c4a35a;'>{cc.get('preview_tp', 0)}</b></span>"
                f"<span>lifecycle-excl <b style='color:#888;'>{cc.get('lifecycle_excluded', 0)}</b></span>"
                f"<span>capability-excl <b style='color:#888;'>{cc.get('capability_excluded', 0)}</b></span>"
                f"<span style='color:#8fd400;'>{matrix.get('view_label') or view_mode}</span>"
                f"</div>"
            )
            html(strip)
            if matrix.get("coverage_warning"):
                st.caption(matrix["coverage_warning"])

            def _private_eval(cell: dict) -> bool:
                if cell.get("availability") == "private-eval":
                    return True
                if cell.get("deployment_channel") == "private-eval-container":
                    return True
                return cell.get("lifecycle") in ("preview", "tech-preview")

            def cell_label(cell: dict | None) -> str:
                if not cell:
                    return '<span style="color:#444;">—</span>'
                rec = cell.get("recommendation", "SUPPORTED")
                live = " ●" if cell.get("endpoint_available") else ""
                aim = cell.get("aim_support", "")
                life = cell.get("lifecycle", "ga")
                excluded = cell.get("lifecycle_excluded")
                cap_excl = cell.get("capability_excluded")
                pe = _private_eval(cell)
                mark = cell.get("matrix_mark")
                life_tag = {
                    "ga": "GA",
                    "preview": "Preview",
                    "tech-preview": "Tech Preview",
                    "planned": "Planned",
                }.get(life, life or "")
                if pe:
                    badge = (
                        '<sup title="Available via private eval container '
                        '(Tech Preview / Preview)" style="color:#c4a35a;font-size:0.65em;'
                        'letter-spacing:0.02em;margin-left:1px;">eval</sup>'
                    )
                else:
                    badge = ""
                if mark == "—" or (cell.get("aim_support") is None and mark in (None, "—")):
                    return '<span style="color:#444;">—</span>'
                if cap_excl:
                    return (
                        f'<span style="color:#777;" title="Capability mismatch — AIM support exists">'
                        f"◌{live}{badge}</span><br/>"
                        f'<span style="color:#555;font-size:0.62rem;">{aim or "aim"} · {life_tag}</span>'
                    )
                if excluded and pe:
                    return (
                        f'<span style="color:#888;" title="Available via private eval '
                        f'container; not production-eligible">○{badge}</span><br/>'
                        f'<span style="color:#666;font-size:0.62rem;">{aim} · {life_tag}</span>'
                    )
                if excluded:
                    return (
                        f'<span style="color:#555;">⊘</span><br/>'
                        f'<span style="color:#444;font-size:0.62rem;">{life_tag}</span>'
                    )
                if mark:
                    color = (
                        "#8fd400"
                        if mark == "★"
                        else "#dafd95"
                        if mark in ("①", "②", "③", "④", "⑤")
                        else "#999"
                        if mark == "✓"
                        else "#666"
                    )
                    weight = "700" if mark == "★" else "500"
                    shown = f'<span style="color:{color};font-weight:{weight};">{mark}{live}{badge}</span>'
                elif rec == "PREFERRED":
                    shown = f'<span style="color:#8fd400;font-weight:700;">★{live}{badge}</span>'
                elif rec in ("RECOMMENDED", "ACCEPTABLE"):
                    shown = f'<span style="color:#999;">✓{live}{badge}</span>'
                else:
                    shown = f'<span style="color:#666;">○{live}{badge}</span>'
                aim_txt = aim if aim is not None else "—"
                return (
                    f'{shown}<br/><span style="color:#555;font-size:0.62rem;">{aim_txt} · {life_tag}</span>'
                )

            status_color = {
                "recommended": "#8fd400",
                "suitable": "#dafd95",
                "supported": "#999",
                "lifecycle_excluded": "#666",
                "capability_excluded": "#777",
                "deployment_excluded": "#666",
                "metadata_incomplete": "#a66",
                "no_supported_compute": "#444",
            }
            header = "".join(
                f'<th style="padding:0.55rem 0.4rem;color:#999;font-size:0.72rem;font-weight:500;'
                f'position:sticky;top:0;background:#141414;z-index:2;">{c}</th>'
                for c in display_cols
            )
            body_rows = []
            for model in row_models:
                status = row_status.get(model, "")
                sc = status_color.get(status, "#666")
                tds = "".join(
                    f'<td style="padding:0.55rem 0.4rem;text-align:center;border-top:1px solid #2a2a2a;vertical-align:top;">{cell_label(matrix["cells"].get(model, {}).get(col))}</td>'
                    for col in display_cols
                )
                short = model if len(model) < 36 else model[:33] + "…"
                body_rows.append(
                    f'<tr><td style="padding:0.55rem 0.5rem;color:#e8e8e8;font-family:IBM Plex Mono,monospace;'
                    f'font-size:0.75rem;border-top:1px solid #2a2a2a;white-space:nowrap;'
                    f'position:sticky;left:0;background:#141414;z-index:1;">'
                    f'{short}<br/><span style="color:{sc};font-size:0.62rem;">{status}</span></td>{tds}</tr>'
                )
            pe_note = matrix.get("private_eval_note") or (
                "Preview / Tech Preview cells on MI350P, R9700, and W7900 are available "
                "via private eval containers (not silent production GA)."
            )
            html(
                f"""
                <p style="color:#666;font-size:0.78rem;margin:0.5rem 0 0.35rem;">★ Preferred · ② ③ numbered top candidates only · ✓ Acceptable · ○ Supported · ◌ Capability mismatch (AIM exists) · ⊘ Lifecycle-excluded · — No AIM support · ● Live · Full rank/score in cell detail</p>
                <p style="color:#999;font-size:0.78rem;margin:0 0 0.65rem;"><sup style="color:#c4a35a;">eval</sup> = available via <strong style="color:#bbb;font-weight:500;">private eval container</strong> (Tech Preview / Preview). Under Production these cells stay visible but tagged — not blank — and are not production-eligible. {pe_note}</p>
                <div style="overflow:auto;max-height:600px;border:1px solid #333;border-radius:0.5rem;background:#141414;margin:0 0 1rem;">
                  <table style="border-collapse:collapse;width:100%;min-width:960px;">
                    <thead><tr>
                      <th style="padding:0.55rem 0.5rem;text-align:left;color:#666;font-size:0.72rem;position:sticky;top:0;left:0;background:#141414;z-index:3;">MODEL / AIM</th>
                      {header}
                    </tr></thead>
                    <tbody>{''.join(body_rows)}</tbody>
                  </table>
                </div>
                """
            )

            st.markdown("#### Cell detail / Simulate route")
            # Inspect any visible model/cell — not only ranked[:12]
            inspect_options: list[str] = []
            inspect_cells: list[dict] = []
            for model in row_models:
                cols = matrix.get("cells", {}).get(model) or {}
                for col in display_cols:
                    cell = cols.get(col)
                    if not cell:
                        continue
                    mark = cell.get("matrix_mark") or "·"
                    rank = cell.get("rank")
                    prefix = f"#{rank}" if rank else mark
                    inspect_options.append(f"{prefix} {model} × {col}")
                    inspect_cells.append(cell)
            if not inspect_options and ranked:
                inspect_options = [f"#{c.get('rank')} {c['model']} × {c['compute']}" for c in ranked[:12]]
                inspect_cells = list(ranked[:12])
            if inspect_options:
                pick = st.selectbox("Inspect candidate", inspect_options)
                detail = inspect_cells[inspect_options.index(pick)]
                model_id = detail.get("model")
                wn = why_not.get(model_id) or []
                st.json(
                    {
                        "model": detail.get("model"),
                        "compute": detail.get("compute"),
                        "row_status": row_status.get(model_id),
                        "why_not_recommended": wn,
                        "recommendation": detail.get("recommendation"),
                        "confidence": detail.get("confidence"),
                        "evidence_badge": detail.get("evidence_badge"),
                        "performance_evidence": detail.get("performance_evidence"),
                        "rank": detail.get("rank"),
                        "score": detail.get("score"),
                        "matrix_mark": detail.get("matrix_mark"),
                        "aim_support": detail.get("aim_support"),
                        "lifecycle": detail.get("lifecycle"),
                        "availability": detail.get("availability"),
                        "deployment_channel": detail.get("deployment_channel"),
                        "production_eligible": detail.get("production_eligible"),
                        "capability_excluded": detail.get("capability_excluded"),
                        "lifecycle_excluded": detail.get("lifecycle_excluded"),
                        "capability_fit": detail.get("capability_fit"),
                        "quality_fit": detail.get("quality_fit"),
                        "performance_fit": detail.get("performance_fit"),
                        "economic_fit": detail.get("economic_fit"),
                        "deployment_fit": detail.get("deployment_fit"),
                        "lifecycle_fit": detail.get("lifecycle_fit"),
                        "serving_pattern_fit": detail.get("serving_pattern_fit"),
                        "locality_fit": detail.get("locality_fit"),
                        "evidence_confidence": detail.get("evidence_confidence"),
                        "preference_label": detail.get("preference_label"),
                        "cost_confidence": detail.get("cost_confidence"),
                        "cost_evidence": detail.get("cost_evidence"),
                        "infrastructure_cost_class": detail.get("infrastructure_cost_class")
                        or detail.get("hardware_cost_class"),
                        "token_economic_fit": detail.get("token_economic_fit"),
                        "relative_cost_class": detail.get("relative_cost_class"),
                        "endpoint_available": detail.get("endpoint_available"),
                        "endpoint_id": detail.get("endpoint_id"),
                        "rationale": detail.get("rationale"),
                        "why": detail.get("reasons"),
                        "policy_override": detail.get("policy_override"),
                        "private_eval_note": (
                            "Available via private eval container (Tech Preview / Preview)"
                            if detail.get("lifecycle") in ("preview", "tech-preview")
                            or detail.get("availability") == "private-eval"
                            else None
                        ),
                        "amd_caveat": (
                            "AMD comparative performance evidence pending — "
                            "missing evidence lowers confidence; not proof of inferiority."
                            if (detail.get("performance_evidence") or {}).get("status")
                            not in ("AMD_MEASURED",)
                            else None
                        ),
                    }
                )
                # Human-readable rationale blocks (avoid Best/Winner/Superior language)
                rat = detail.get("rationale") or {}
                if rat:
                    st.markdown("**Why recommended (policy rationale)**")
                    for block in ("eligibility", "strengths", "weaknesses", "evidence", "uncertainties"):
                        items = rat.get(block) or []
                        if items:
                            st.caption(block.replace("_", " ").title() + ": " + " · ".join(items[:4]))
                pe = detail.get("performance_evidence") or {}
                if pe.get("status") and pe.get("status") != "AMD_MEASURED":
                    st.caption(
                        f"Evidence badge {detail.get('evidence_badge') or '?'} · "
                        f"performance_evidence={pe.get('status')} · "
                        "AMD comparative pending."
                    )
                # Alternatives / why not peer (top other ranked on same compute)
                alts = [
                    c
                    for c in ranked
                    if c.get("compute") == detail.get("compute")
                    and c.get("model") != detail.get("model")
                ][:3]
                if alts:
                    st.markdown("**Alternatives (same compute)**")
                    for alt in alts:
                        st.caption(
                            f"· {alt.get('model')} — {alt.get('recommendation')} · "
                            f"confidence {alt.get('confidence')} · "
                            f"badge {alt.get('evidence_badge')}"
                        )
                # Compact model-evidence detail
                try:
                    mmeta = engine.models.get(model_id) or {}
                    if mmeta:
                        with st.expander("Model evidence (compact)"):
                            st.write(
                                {
                                    "capabilities": mmeta.get("capabilities"),
                                    "strengths": mmeta.get("strengths"),
                                    "evidence": mmeta.get("evidence"),
                                    "provenance_sources": (mmeta.get("provenance") or {}).get(
                                        "sources"
                                    ),
                                    "reviewed": (mmeta.get("provenance") or {}).get("reviewed"),
                                }
                            )
                except Exception:
                    pass
                if wn and row_status.get(model_id) != "recommended":
                    st.caption("Why not recommended: " + " · ".join(wn[:3]))

            if st.button("Simulate runtime route"):
                sim = engine.simulate_route(
                    uc_opts[uc_label],
                    objective=obj_opts[obj_label],
                    utilization=util,
                    endpoints=endpoints,
                    lifecycle_mode=life_mode,
                    data_locality=data_loc,
                    serving_pattern=serve_pattern,
                )
                st.markdown("**Simulate Route**")
                st.write(
                    f"Eligible cells: {sim['eligible_combinations']} · "
                    f"Objective: {sim['objective']} · Traffic: {sim['utilization']} · "
                    f"Serving: {sim.get('serving_pattern')} · Latency: {sim.get('latency_requirement')} · "
                    f"Lifecycle: {sim.get('lifecycle_mode')}"
                )
                st.write("AMD recommendation (top):")
                for r in sim["amd_recommendation"][:4]:
                    st.caption(
                        f"#{r.get('rank')} {r['model']} × {r['compute']} "
                        f"({r['recommendation']} · {r.get('lifecycle')})"
                    )
                st.write("Currently deployed eligible:")
                for r in sim["currently_deployed_eligible"][:4]:
                    st.caption(f"● {r['model']} × {r['compute']} ({r.get('endpoint_id')})")
                excl_blocks = sim.get("exclusions") or {}
                life_excl = excl_blocks.get("lifecycle") or sim.get("lifecycle_exclusions") or []
                if life_excl:
                    st.write(f"Lifecycle exclusions ({len(life_excl)}):")
                    for e in life_excl[:5]:
                        st.caption(
                            f"⊘ {e['model']} × {e['compute']} [{e.get('lifecycle')}] — {e.get('exclusion_reason')}"
                        )
                sp_excl = excl_blocks.get("serving_pattern_latency") or sim.get(
                    "serving_pattern_exclusions"
                ) or []
                if sp_excl:
                    st.write(f"Serving-pattern / latency notes ({len(sp_excl)}):")
                    for e in sp_excl[:4]:
                        st.caption(f"· {e['model']} × {e['compute']} (EPYC vs interactive+high)")
                loc_excl = excl_blocks.get("locality") or sim.get("locality_exclusions") or []
                if loc_excl:
                    st.write(f"Locality soft-exclusions ({len(loc_excl)}):")
                    for e in loc_excl[:4]:
                        st.caption(
                            f"· {e.get('model')} × {e.get('compute')} — {e.get('exclusion_reason')}"
                        )
                sel = sim.get("selected_runtime_route")
                st.success(
                    f"Selected: {sel['model']} × {sel['compute']}"
                    if sel
                    else "No deployed eligible endpoint"
                )
                st.caption(sim.get("explanation", ""))
                if sim.get("locality_note"):
                    st.warning(sim["locality_note"])

            st.caption(
                f"Policy {matrix.get('policy_version')} · published {matrix.get('published')} · "
                f"cost={matrix.get('cost_data')} · serving={matrix.get('serving_pattern')} · "
                f"latency={matrix.get('latency_requirement')} · "
                f"lifecycle={matrix.get('lifecycle_mode')} · "
                f"visible={matrix['counts']['visible']} · "
                f"excluded={matrix['counts'].get('lifecycle_excluded', 0)} · "
                f"deployed={matrix['counts']['deployed']}"
            )
    except Exception as exc:
        st.error(f"Routing matrix unavailable: {exc}")

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
    from views.policies import render_policies_tab

    render_policies_tab(meta, section=section, html=html)

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
