"""Live route-flow strip for the Playground operator console."""

from __future__ import annotations

import html as html_lib
from typing import Any

from components.request_state import RequestState, stream_path_label

NODE_ORDER = (
    ("client", "CLIENT"),
    ("gateway", "ENVOY AI GATEWAY"),
    ("router", "vLLM SEMANTIC ROUTER"),
    ("policy", "AMD POLICY"),
    ("aim", "AIM / AMD COMPUTE"),
)


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value))


def _connector_class(left: str, right: str) -> str:
    """Stage-by-stage connector animation based on adjacent node statuses."""
    order = {"idle": 0, "active": 1, "complete": 2, "warning": 2, "failed": 3}
    lv, rv = order.get(left, 0), order.get(right, 0)
    if left == "failed" or right == "failed":
        return "tf-pg-conn failed"
    if left == "warning" or right == "warning":
        if lv >= 1 and rv >= 1:
            return "tf-pg-conn warning on"
        return "tf-pg-conn warning"
    if left == "complete" and right in ("complete", "active", "warning"):
        return "tf-pg-conn on"
    if left == "complete" and right == "idle":
        return "tf-pg-conn"
    if left == "active" or right == "active":
        return "tf-pg-conn pulse"
    return "tf-pg-conn"


def render_route_flow_html(state: RequestState, *, selected: str | None = None) -> str:
    """Return HTML for the persistent live flow (~80–110px)."""
    nodes_html: list[str] = []
    for idx, (nid, label) in enumerate(NODE_ORDER):
        node = state.nodes.get(nid)
        status = node.status if node else "idle"
        detail = (node.detail if node else "") or ""
        if not detail and status == "idle":
            detail = "idle"
        sel = " selected" if selected == nid else ""
        nodes_html.append(
            f'<div class="tf-pg-node {status}{sel}" data-node="{_esc(nid)}" '
            f'title="{_esc(label)}: {_esc(detail)}">'
            f'<span class="tf-pg-node-label">{_esc(label)}</span>'
            f'<span class="tf-pg-node-detail">{_esc(detail)}</span>'
            f"</div>"
        )
        if idx < len(NODE_ORDER) - 1:
            nxt = NODE_ORDER[idx + 1][0]
            left_s = state.nodes.get(nid).status if state.nodes.get(nid) else "idle"
            right_s = state.nodes.get(nxt).status if state.nodes.get(nxt) else "idle"
            nodes_html.append(
                f'<div class="{_connector_class(left_s, right_s)}" aria-hidden="true">'
                f'<span class="tf-pg-conn-line"></span></div>'
            )

    path_note = stream_path_label(state)
    badge = ""
    if state.fallback:
        badge = '<span class="tf-pg-flow-badge warn">fallback</span>'
    elif state.stage == "streaming" and state.saw_content:
        badge = '<span class="tf-pg-flow-badge ok">streaming</span>'
    elif state.stage == "complete":
        badge = '<span class="tf-pg-flow-badge ok">complete</span>'
    elif state.stage == "failed":
        badge = '<span class="tf-pg-flow-badge bad">failed</span>'
    elif state.stage != "idle":
        badge = f'<span class="tf-pg-flow-badge">{_esc(state.stage)}</span>'

    timings = []
    if state.classify_ms is not None:
        timings.append(f"classify {state.classify_ms}ms")
    if state.ttft_ms is not None:
        timings.append(f"TTFT {state.ttft_ms}ms")
    if state.total_ms is not None and state.stage in ("complete", "failed"):
        timings.append(f"total {state.total_ms}ms")
    timing_html = (
        f'<span class="tf-pg-flow-timings">{_esc(" · ".join(timings))}</span>'
        if timings
        else ""
    )

    idle_hint = ""
    if state.stage == "idle":
        idle_hint = (
            '<p class="tf-pg-flow-hint">Send a prompt — classification, policy, and '
            "stream path light up stage-by-stage.</p>"
        )

    return f"""
    <div class="tf-pg-flow" role="group" aria-label="Live request flow">
      <div class="tf-pg-flow-meta">
        <span class="tf-pg-flow-title">Live flow</span>
        {badge}
        <span class="tf-pg-flow-path">{_esc(path_note)}</span>
        {timing_html}
      </div>
      <div class="tf-pg-flow-track">{"".join(nodes_html)}</div>
      {idle_hint}
    </div>
    """
