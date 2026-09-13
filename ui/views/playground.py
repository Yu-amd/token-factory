"""Playground tab — compact single-screen operator / demo console."""

from __future__ import annotations

import html as html_lib
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

import streamlit as st

_UI_ROOT = Path(__file__).resolve().parents[1]
if str(_UI_ROOT) not in sys.path:
    sys.path.insert(0, str(_UI_ROOT))

from components.request_state import (
    RequestState,
    apply_classify,
    apply_resolved_route,
    caption_line,
    enrich_policy_from_metadata,
    mark_classifying,
    mark_complete,
    mark_failed,
    mark_fallback,
    mark_first_token,
    mark_streaming,
    new_request_state,
)
from components.route_flow import render_route_flow_html
from components.route_inspector import render_route_inspector

HtmlFn = Callable[[str], None]
StreamFn = Callable[..., Iterator[str]]
ChatFn = Callable[[str, str], dict[str, Any]]
ExtractFn = Callable[[dict[str, Any]], str]
ProbeFn = Callable[[str, str], str]

SAMPLE_PROMPTS = (
    "Write a ROCm kernel sketch in Python",
    "Explain MI300X vs MI350P for inference",
    "Summarize AMD Instinct positioning for RAG",
)

PLAYGROUND_CSS = """
<style>
/* ---- Playground-only shell (does not affect Matrix/Policies scroll) ---- */
:root {
  /* Overhead above+below conversation pane (chrome, tabs, health, flow, samples, composer). */
  --tf-pg-chrome: 600px;
  --tf-pg-samples: 48px;
}
.tf-pg-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0 0 0.1rem;
}
.tf-pg-header h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--tf-text);
  letter-spacing: -0.01em;
}
.tf-pg-header p {
  margin: 0;
  font-size: 0.72rem;
  color: var(--tf-muted);
}
.tf-pg-health {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.85rem;
  padding: 0.25rem 0.55rem;
  background: var(--tf-surface);
  border: 1px solid var(--tf-border);
  border-radius: 0.4rem;
  font-size: 0.72rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  margin-bottom: 0.2rem;
}
.tf-pg-health-item {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--tf-muted);
  white-space: nowrap;
}
.tf-pg-health-item .tf-dot { width: 7px; height: 7px; border-radius: 50%; }
.tf-pg-health-item.tf-up { color: var(--tf-green-hi); }
.tf-pg-health-item.tf-up .tf-dot {
  background: var(--tf-green); box-shadow: 0 0 8px rgba(118,185,0,0.5);
}
.tf-pg-health-item.tf-down { color: #fca5a5; }
.tf-pg-health-item.tf-down .tf-dot {
  background: var(--tf-danger); box-shadow: 0 0 8px rgba(239,68,68,0.4);
}
.tf-pg-health-item.tf-warn { color: #fcd34d; }
.tf-pg-health-item.tf-warn .tf-dot { background: var(--tf-warn); }

.tf-pg-flow {
  background: #0d0d0d;
  border: 1px solid var(--tf-border);
  border-radius: 0.45rem;
  padding: 0.3rem 0.55rem 0.35rem;
  min-height: 72px;
  max-height: 92px;
  margin-bottom: 0.2rem;
}
.tf-pg-flow-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.65rem;
  margin-bottom: 0.35rem;
  font-size: 0.68rem;
}
.tf-pg-flow-title {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--tf-faint);
  font-weight: 600;
}
.tf-pg-flow-path {
  color: var(--tf-muted);
  font-family: "IBM Plex Mono", ui-monospace, monospace;
}
.tf-pg-flow-timings {
  margin-left: auto;
  color: var(--tf-cyan);
  font-family: "IBM Plex Mono", ui-monospace, monospace;
}
.tf-pg-flow-badge {
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--tf-border);
  color: var(--tf-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.62rem;
}
.tf-pg-flow-badge.ok {
  color: var(--tf-green-hi);
  border-color: rgba(118,185,0,0.35);
  background: var(--tf-green-dim);
}
.tf-pg-flow-badge.warn {
  color: #fcd34d;
  border-color: rgba(245,158,11,0.4);
  background: rgba(245,158,11,0.1);
}
.tf-pg-flow-badge.bad {
  color: #fca5a5;
  border-color: rgba(239,68,68,0.4);
  background: rgba(239,68,68,0.1);
}
.tf-pg-flow-track {
  display: flex;
  align-items: stretch;
  gap: 0.2rem;
  min-height: 42px;
}
.tf-pg-node {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.15rem;
  padding: 0.35rem 0.4rem;
  border-radius: 0.35rem;
  border: 1px solid var(--tf-border);
  background: var(--tf-elevated);
  color: var(--tf-muted);
  text-align: left;
  cursor: default;
  transition: border-color 0.15s, background 0.15s, box-shadow 0.15s;
}
.tf-pg-node-label {
  font-size: 0.62rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #b0b0b0;
  font-weight: 650;
  line-height: 1.2;
}
.tf-pg-node-detail {
  font-size: 0.7rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #8a8a8a;
}
.tf-pg-node.active .tf-pg-node-detail,
.tf-pg-node.complete .tf-pg-node-detail,
.tf-pg-node.warning .tf-pg-node-detail,
.tf-pg-node.failed .tf-pg-node-detail { color: inherit; }
.tf-pg-node.active .tf-pg-node-label,
.tf-pg-node.complete .tf-pg-node-label,
.tf-pg-node.warning .tf-pg-node-label,
.tf-pg-node.failed .tf-pg-node-label { color: inherit; opacity: 0.85; }
.tf-pg-node.active {
  border-color: rgba(0,212,255,0.55);
  color: var(--tf-cyan);
  box-shadow: 0 0 12px rgba(0,212,255,0.12);
}
.tf-pg-node.complete {
  border-color: rgba(118,185,0,0.45);
  color: var(--tf-green-hi);
}
.tf-pg-node.warning {
  border-color: rgba(245,158,11,0.55);
  color: #fcd34d;
}
.tf-pg-node.failed {
  border-color: rgba(239,68,68,0.55);
  color: #fca5a5;
}
.tf-pg-node.selected { outline: 1px solid var(--tf-green-hi); }
.tf-pg-conn {
  flex: 0 0 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.tf-pg-conn-line {
  display: block;
  width: 100%;
  height: 2px;
  background: #2a2a2a;
  border-radius: 2px;
  overflow: hidden;
}
.tf-pg-conn.on .tf-pg-conn-line { background: rgba(118,185,0,0.65); }
.tf-pg-conn.warning .tf-pg-conn-line,
.tf-pg-conn.warning.on .tf-pg-conn-line { background: rgba(245,158,11,0.7); }
.tf-pg-conn.failed .tf-pg-conn-line { background: rgba(239,68,68,0.7); }
.tf-pg-conn.pulse .tf-pg-conn-line {
  background: linear-gradient(90deg, #2a2a2a, var(--tf-cyan), #2a2a2a);
  background-size: 200% 100%;
  animation: tf-pg-pulse 1.1s linear infinite;
}
@keyframes tf-pg-pulse {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
.tf-pg-flow-hint {
  margin: 0.3rem 0 0;
  font-size: 0.7rem;
  color: var(--tf-faint);
}
.tf-pg-insp-head { margin-bottom: 0.25rem; }
.tf-pg-insp-title {
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--tf-faint);
  font-weight: 600;
}
.tf-pg-kv {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.tf-pg-kv-row {
  display: grid;
  grid-template-columns: 7.25rem 1fr;
  gap: 0.35rem;
  font-size: 0.78rem;
}
.tf-pg-kv-row dt {
  margin: 0;
  color: var(--tf-faint);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 0.62rem;
  padding-top: 0.15rem;
}
.tf-pg-kv-row dd {
  margin: 0;
  color: var(--tf-text);
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.75rem;
  word-break: break-word;
}
.tf-pg-insp-note {
  margin: 0.55rem 0 0;
  font-size: 0.7rem;
  color: var(--tf-faint);
  line-height: 1.4;
}
.tf-pg-insp-note.warn { color: #fcd34d; }
.tf-pg-insp-note.bad { color: #fca5a5; }
.tf-pg-insp-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.65rem;
}
.tf-pg-insp-links .tf-link {
  padding: 0.35rem 0.7rem !important;
  font-size: 0.72rem !important;
}
.tf-pg-empty {
  padding: 0.75rem 0.65rem;
  text-align: center;
  color: var(--tf-muted);
  font-size: 0.85rem;
  line-height: 1.5;
  border: 1px dashed var(--tf-border);
  border-radius: 0.45rem;
  background: rgba(255,255,255,0.015);
}
.tf-pg-empty strong { color: var(--tf-text); font-weight: 600; }
.tf-pg-pane-chat, .tf-pg-pane-insp { display: none; }

/*
 * Viewport-fit panes (Playground tab only). Streamlit/emotion sets a fixed px
 * `height` on stLayoutWrapper; `height: auto` + matching min/max calc beats that
 * so panes shrink on short laptops and grow on taller viewports. Other tabs keep
 * normal document scroll (inactive panels are display:none; selectors stay scoped).
 */
[data-testid="stTabPanel"]:has(.tf-pg-header)
  [data-testid="stLayoutWrapper"]:has(.tf-pg-pane-chat) {
  height: auto !important;
  min-height: calc(100vh - var(--tf-pg-chrome)) !important;
  max-height: calc(100vh - var(--tf-pg-chrome)) !important;
}
[data-testid="stTabPanel"]:has(.tf-pg-header)
  [data-testid="stLayoutWrapper"]:has(.tf-pg-pane-insp) {
  height: auto !important;
  min-height: calc(100vh - var(--tf-pg-chrome) + var(--tf-pg-samples)) !important;
  max-height: calc(100vh - var(--tf-pg-chrome) + var(--tf-pg-samples)) !important;
}
[data-testid="stTabPanel"]:has(.tf-pg-header)
  [data-testid="stLayoutWrapper"]:has(.tf-pg-pane-chat) [data-testid="stVerticalBlock"],
[data-testid="stTabPanel"]:has(.tf-pg-header)
  [data-testid="stLayoutWrapper"]:has(.tf-pg-pane-insp) [data-testid="stVerticalBlock"] {
  height: 100% !important;
  max-height: 100% !important;
}
[data-testid="stTabPanel"]:has(.tf-pg-header) [data-testid="stChatInput"] {
  padding-top: 0 !important;
}
[data-testid="stTabPanel"]:has(.tf-pg-header)
  [data-testid="stElementContainer"]:has([data-testid="stChatInput"]) {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
</style>
"""


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value))


def _health_class(value: str) -> str:
    if value == "UP":
        return "tf-up"
    if value.startswith("HTTP"):
        return "tf-warn"
    return "tf-down"


def render_compact_health(checks: list[tuple[str, str]], *, html: HtmlFn) -> None:
    items = []
    for name, value in checks:
        cls = _health_class(value)
        items.append(
            f'<span class="tf-pg-health-item {cls}">'
            f'<span class="tf-dot"></span>{_esc(name)}'
            f'<span style="opacity:0.55;margin-left:0.25rem">{_esc(value)}</span>'
            f"</span>"
        )
    html(f'<div class="tf-pg-health">{"".join(items)}</div>')


def _lookup_route(ui_meta: dict[str, Any], route_name: str | None) -> dict[str, Any] | None:
    if not route_name:
        return None
    for route in ui_meta.get("routes") or []:
        if route.get("name") == route_name:
            return route
    return None


def _optional_recommendation(
    use_case: str | None,
    objective: str | None,
    endpoints: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not use_case:
        return {}
    try:
        root = Path(__file__).resolve().parents[2]
        src = str(root / "src")
        if src not in sys.path:
            sys.path.insert(0, src)
        from token_factory.routing_matrix import RecommendationEngine

        eng = RecommendationEngine()
        rec = eng.recommend(
            use_case,
            objective=objective or "balanced",
            endpoints=endpoints,
            limit=3,
        )
        return {
            "use_case": rec.get("use_case") or use_case,
            "objective": rec.get("objective"),
            "serving_pattern": rec.get("serving_pattern"),
            "preference_label": rec.get("preference_label"),
        }
    except Exception:
        return {"use_case": use_case}


def render_playground_tab(
    *,
    meta: dict[str, Any],
    links: dict[str, str],
    virtual_model: str,
    sr_api: str,
    direct_stream: bool,
    probe_defs: list[tuple[str, str, str]],
    probe: ProbeFn,
    stream_chat_completion: StreamFn,
    chat_completion: ChatFn,
    extract_reply: ExtractFn,
    html: HtmlFn,
) -> None:
    """Compact Playground: health + live flow + conversation | inspector + composer."""
    html(PLAYGROUND_CSS)

    if "pg_request" not in st.session_state:
        st.session_state.pg_request = new_request_state(direct_stream=direct_stream)
    if "pg_selected_node" not in st.session_state:
        st.session_state.pg_selected_node = None
    if "pg_pending_prompt" not in st.session_state:
        st.session_state.pg_pending_prompt = None

    state: RequestState = st.session_state.pg_request

    html(
        f"""
        <div class="tf-pg-header">
          <h2>Playground</h2>
          <p>Operator console · {_esc(virtual_model)} ·
             path {"direct AIM" if direct_stream else "gateway only"}</p>
        </div>
        """
    )

    checks = [(n, probe(u, p)) for n, u, p in probe_defs]
    render_compact_health(checks, html=html)

    flow_slot = st.empty()

    def _paint_flow() -> None:
        flow_slot.html(
            render_route_flow_html(
                st.session_state.pg_request,
                selected=st.session_state.pg_selected_node,
            )
        )

    _paint_flow()

    left, right = st.columns([7.1, 2.9], gap="small")
    # Fallback px if CSS calc is unavailable; PLAYGROUND_CSS overrides via 100vh.
    chat_height = 300

    with left:
        with st.container(height=chat_height, border=False):
            html('<div class="tf-pg-pane-chat" aria-hidden="true"></div>')
            if not st.session_state.messages:
                html(
                    """
                    <div class="tf-pg-empty">
                      <strong>No turns yet.</strong><br/>
                      Watch the live flow above as classify → policy → AIM advances.
                      Composer stays pinned below.
                    </div>
                    """
                )
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg.get("meta"):
                        st.caption(msg["meta"])

        s1, s2, s3, s4 = st.columns([1, 1, 1, 0.55])
        for col, sample in zip((s1, s2, s3), SAMPLE_PROMPTS):
            with col:
                short = sample if len(sample) <= 40 else sample[:37] + "…"
                if st.button(short, key=f"pg_sample_{abs(hash(sample)) % 10_000_000}"):
                    st.session_state.pg_pending_prompt = sample
                    st.rerun()
        with s4:
            if st.button("Clear", key="pg_clear"):
                st.session_state.messages = []
                st.session_state.pg_request = new_request_state(
                    direct_stream=direct_stream
                )
                st.rerun()

    with right:
        with st.container(height=chat_height + 48, border=True):
            html('<div class="tf-pg-pane-insp" aria-hidden="true"></div>')
            render_route_inspector(state, links=links, html=html)

    prompt = st.chat_input("Ask Token Factory… e.g. Write a ROCm kernel sketch in Python")
    if st.session_state.pg_pending_prompt and not prompt:
        prompt = st.session_state.pg_pending_prompt
        st.session_state.pg_pending_prompt = None

    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})

    state = new_request_state(direct_stream=direct_stream)
    mark_classifying(state)
    st.session_state.pg_request = state
    _paint_flow()

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        stream_meta: dict[str, Any] = {
            "model": None,
            "finish": None,
            "saw_content": False,
            "saw_reasoning": False,
            "gateway_buffered": False,
        }
        status = st.empty()
        status.caption("Classifying intent…")

        def on_event(name: str, payload: dict[str, Any]) -> None:
            nonlocal state
            if name == "classifying":
                mark_classifying(state)
                status.caption("Classifying intent…")
            elif name == "classified":
                classified = payload.get("classified") or {}
                apply_classify(
                    state,
                    classified,
                    classify_ms=payload.get("classify_ms"),
                )
                route_name = str(payload.get("route") or "")
                model_id = str(payload.get("model_id") or "")
                route = _lookup_route(meta, route_name)
                ep = (route or {}).get("endpoint") or {}
                pol = enrich_policy_from_metadata(meta, route_name, ep)
                rec = _optional_recommendation(
                    pol.get("use_case"),
                    pol.get("objective_alias"),
                    meta.get("endpoints"),
                )
                apply_resolved_route(
                    state,
                    route_name=route_name,
                    model_id=model_id,
                    endpoint=ep,
                    aim_url=payload.get("aim_url"),
                    policy_meta=pol,
                    recommendation=rec,
                )
                status.caption(f"Routed {route_name} · opening stream…")
            elif name == "fallback":
                mark_fallback(state, str(payload.get("reason") or "direct AIM failed"))
                status.caption("Direct AIM failed — gateway fallback…")
            elif name == "streaming":
                mark_streaming(state, str(payload.get("stream_path") or "gateway"))
            st.session_state.pg_request = state
            _paint_flow()

        try:

            def _stream() -> Iterator[str]:
                first = True
                saw_token = False
                for piece in stream_chat_completion(
                    prompt,
                    virtual_model,
                    stream_meta,
                    meta,
                    sr_api,
                    on_event=on_event,
                ):
                    if first:
                        status.empty()
                        first = False
                    if not saw_token:
                        saw_token = True
                        content = bool(stream_meta.get("saw_content"))
                        reasoning = bool(stream_meta.get("saw_reasoning"))
                        mark_first_token(state, content=content or not reasoning)
                        st.session_state.pg_request = state
                        _paint_flow()
                    elif stream_meta.get("saw_content") and not state.saw_content:
                        mark_first_token(state, content=True)
                        st.session_state.pg_request = state
                        _paint_flow()
                    yield piece

            reply = st.write_stream(_stream())
            if not (reply or "").strip():
                status.empty()
                body = chat_completion(prompt, virtual_model)
                reply = extract_reply(body)
                stream_meta["model"] = body.get("model")
                stream_meta["finish"] = (body.get("choices") or [{}])[0].get(
                    "finish_reason"
                )
                stream_meta["stream_path"] = stream_meta.get("stream_path") or "gateway"
                if not state.stream_path:
                    mark_streaming(state, "gateway")
                st.markdown(reply)

            state.model = stream_meta.get("model") or state.model
            state.finish = stream_meta.get("finish")
            state.gateway_buffered = bool(stream_meta.get("gateway_buffered"))
            state.saw_content = bool(stream_meta.get("saw_content")) or state.saw_content
            state.saw_reasoning = (
                bool(stream_meta.get("saw_reasoning")) or state.saw_reasoning
            )
            if stream_meta.get("stream_path"):
                state.stream_path = stream_meta["stream_path"]
            if stream_meta.get("classify_ms") is not None:
                state.classify_ms = stream_meta["classify_ms"]
            if stream_meta.get("direct_error") and not state.fallback:
                mark_fallback(state, str(stream_meta["direct_error"]))
            mark_complete(state)
            meta_line = caption_line(state)
            st.caption(meta_line)
            st.session_state.messages.append(
                {"role": "assistant", "content": reply, "meta": meta_line}
            )
            st.session_state.pg_request = state
            _paint_flow()
            st.rerun()
        except Exception as exc:
            status.empty()
            mark_failed(state, str(exc))
            st.session_state.pg_request = state
            _paint_flow()
            err = (
                f"{exc} — check SR API (:8081) and AIM endpoints; "
                "or run token-factory ports start"
            )
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err})
