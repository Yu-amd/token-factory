"""Per-request Playground state + real timing helpers (pure, unit-testable)."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

NodeId = Literal["client", "gateway", "router", "policy", "aim"]
NodeStatus = Literal["idle", "active", "complete", "warning", "failed"]
Stage = Literal[
    "idle",
    "classifying",
    "resolving",
    "streaming",
    "complete",
    "failed",
]

# Soft route-name → matrix use-case (structural mapping, not a fabricated score).
ROUTE_USE_CASE: dict[str, str] = {
    "coding_route": "coding-assistant",
    "reasoning_route": "mathematical-reasoning",
    "general_route": "simple-chat",
}

ROLE_USE_CASE: dict[str, str] = {
    "coding": "coding-assistant",
    "math": "mathematical-reasoning",
    "reasoning": "general-reasoning",
    "general": "simple-chat",
}


@dataclass
class NodeState:
    status: NodeStatus = "idle"
    detail: str = ""


def _idle_nodes() -> dict[str, NodeState]:
    return {
        "client": NodeState(),
        "gateway": NodeState(),
        "router": NodeState(),
        "policy": NodeState(),
        "aim": NodeState(),
    }


@dataclass
class RequestState:
    """Live request object driving the flow strip + route inspector."""

    stage: Stage = "idle"
    nodes: dict[str, NodeState] = field(default_factory=_idle_nodes)
    classification: str | None = None
    confidence: float | None = None
    route: str | None = None
    model: str | None = None
    compute: str | None = None
    hardware: str | None = None
    accelerator: str | None = None
    role: str | None = None
    domains: list[str] = field(default_factory=list)
    objective: str | None = None
    serving_pattern: str | None = None
    preference_label: str | None = None
    policy_profile: str | None = None
    use_case: str | None = None
    stream_path: str | None = None  # "direct-aim" | "gateway"
    preferred_path: str = "direct-aim"
    fallback: bool = False
    fallback_reason: str | None = None
    gateway_buffered: bool = False
    classify_ms: int | None = None
    ttft_ms: int | None = None
    total_ms: int | None = None
    finish: str | None = None
    error: str | None = None
    saw_content: bool = False
    saw_reasoning: bool = False
    t0: float | None = None
    stream_t0: float | None = None
    aim_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return raw


def new_request_state(*, direct_stream: bool = True) -> RequestState:
    preferred = "direct-aim" if direct_stream else "gateway"
    state = RequestState(preferred_path=preferred)
    if not direct_stream:
        state.stream_path = "gateway"
    return state


def elapsed_ms(t0: float | None, now: float | None = None) -> int | None:
    if t0 is None:
        return None
    return int(((now if now is not None else time.perf_counter()) - t0) * 1000)


def _set_node(
    state: RequestState, node: NodeId, status: NodeStatus, detail: str = ""
) -> None:
    state.nodes[node] = NodeState(status=status, detail=detail)


def mark_classifying(state: RequestState) -> RequestState:
    state.stage = "classifying"
    state.t0 = time.perf_counter()
    _set_node(state, "client", "complete", "prompt sent")
    _set_node(state, "gateway", "active", "hand-off")
    _set_node(state, "router", "active", "classifying…")
    _set_node(state, "policy", "idle")
    _set_node(state, "aim", "idle")
    return state


def apply_classify(
    state: RequestState,
    classified: dict[str, Any],
    *,
    classify_ms: int | None = None,
) -> RequestState:
    decision = (
        classified.get("routing_decision")
        or (classified.get("classification") or {}).get("category")
        or ""
    )
    conf = (classified.get("classification") or {}).get("confidence")
    if conf is None:
        conf = (classified.get("decision_result") or {}).get("confidence")
    signals = classified.get("matched_signals") or {}
    domains = list(signals.get("domains") or [])
    state.classification = str(decision) if decision else None
    state.confidence = float(conf) if conf is not None else None
    state.domains = domains
    if classify_ms is not None:
        state.classify_ms = classify_ms
    elif (classified.get("classification") or {}).get("processing_time_ms") is not None:
        state.classify_ms = int(
            (classified.get("classification") or {})["processing_time_ms"]
        )
    conf_txt = (
        f"{state.confidence:.3f}" if isinstance(state.confidence, float) else "—"
    )
    detail = f"{state.classification or '—'} · conf {conf_txt}"
    _set_node(state, "gateway", "complete", "classified path")
    _set_node(state, "router", "complete", detail)
    state.stage = "resolving"
    _set_node(state, "policy", "active", "resolving…")
    return state


def guess_use_case(route_name: str | None, role: str | None = None) -> str | None:
    if route_name and route_name in ROUTE_USE_CASE:
        return ROUTE_USE_CASE[route_name]
    if role and role in ROLE_USE_CASE:
        return ROLE_USE_CASE[role]
    return None


def apply_resolved_route(
    state: RequestState,
    *,
    route_name: str,
    model_id: str,
    endpoint: dict[str, Any] | None = None,
    aim_url: str | None = None,
    policy_meta: dict[str, Any] | None = None,
    recommendation: dict[str, Any] | None = None,
) -> RequestState:
    ep = endpoint or {}
    state.route = route_name
    state.model = model_id
    state.aim_url = aim_url
    state.hardware = ep.get("hardware")
    state.accelerator = ep.get("accelerator")
    state.role = ep.get("role")
    hw_parts = [p for p in (state.hardware, state.accelerator) if p]
    state.compute = " · ".join(hw_parts) if hw_parts else None

    pol = policy_meta or {}
    state.policy_profile = (
        pol.get("active_profile") or pol.get("policy_name") or state.policy_profile
    )
    state.objective = (
        pol.get("objective_alias")
        or (pol.get("routing_matrix") or {}).get("objective_alias")
        or state.objective
    )

    rec = recommendation or {}
    if rec.get("objective"):
        state.objective = str(rec["objective"])
    if rec.get("serving_pattern"):
        state.serving_pattern = str(rec["serving_pattern"])
    if rec.get("preference_label"):
        state.preference_label = str(rec["preference_label"])
    if rec.get("use_case"):
        state.use_case = str(rec["use_case"])
    else:
        state.use_case = guess_use_case(route_name, state.role)

    pol_bits = [b for b in (state.objective, state.serving_pattern) if b]
    _set_node(
        state,
        "policy",
        "complete",
        " · ".join(pol_bits) if pol_bits else (state.role or "policy"),
    )
    aim_bits = [b for b in (state.model, state.compute) if b]
    _set_node(
        state,
        "aim",
        "active",
        " · ".join(aim_bits) if aim_bits else "connecting…",
    )
    return state


def mark_streaming(state: RequestState, stream_path: str) -> RequestState:
    state.stage = "streaming"
    state.stream_path = stream_path
    state.stream_t0 = time.perf_counter()
    if stream_path == "gateway":
        _set_node(state, "gateway", "active", "gateway SSE")
        if state.preferred_path == "direct-aim" and state.fallback:
            _set_node(state, "gateway", "warning", "fallback SSE")
    else:
        _set_node(state, "gateway", "complete", "classify only")
    _set_node(state, "aim", "active", state.nodes["aim"].detail or "streaming…")
    return state


def mark_fallback(state: RequestState, reason: str) -> RequestState:
    state.fallback = True
    state.fallback_reason = reason[:240]
    state.stream_path = "gateway"
    _set_node(state, "gateway", "warning", "fallback")
    if state.nodes["router"].status == "idle":
        _set_node(state, "router", "warning", "skipped / failed")
    if state.nodes["policy"].status not in ("complete",):
        _set_node(state, "policy", "warning", "gateway path")
    return state


def mark_first_token(
    state: RequestState, *, content: bool = True, now: float | None = None
) -> RequestState:
    ts = now if now is not None else time.perf_counter()
    if content:
        state.saw_content = True
    else:
        state.saw_reasoning = True
    if state.ttft_ms is None and state.stream_t0 is not None:
        state.ttft_ms = elapsed_ms(state.stream_t0, ts)
    detail = state.nodes["aim"].detail or ""
    if "Streaming" not in detail:
        base = detail.split(" · Streaming")[0] if detail else (state.model or "AIM")
        _set_node(state, "aim", "active", f"{base} · Streaming")
    return state


def mark_complete(state: RequestState, *, now: float | None = None) -> RequestState:
    state.stage = "complete"
    state.total_ms = elapsed_ms(state.t0, now)
    for node in ("client", "gateway", "router", "policy", "aim"):
        cur = state.nodes[node]
        if cur.status == "active":
            _set_node(state, node, "complete", cur.detail)  # type: ignore[arg-type]
        elif cur.status == "idle" and node == "gateway" and state.stream_path == "direct-aim":
            _set_node(state, "gateway", "complete", "classify only")
    if state.fallback:
        _set_node(state, "gateway", "warning", state.nodes["gateway"].detail or "fallback")
    return state


def mark_failed(state: RequestState, error: str) -> RequestState:
    state.stage = "failed"
    state.error = error[:400]
    state.total_ms = elapsed_ms(state.t0)
    # Mark the furthest active node as failed.
    for node in ("aim", "policy", "router", "gateway", "client"):
        if state.nodes[node].status in ("active", "warning"):
            _set_node(state, node, "failed", state.nodes[node].detail or "error")  # type: ignore[arg-type]
            break
    else:
        _set_node(state, "client", "failed", "error")
    return state


def stream_path_label(state: RequestState) -> str:
    if state.stream_path == "direct-aim":
        return "direct AIM (SR classify → AIM stream)"
    if state.stream_path == "gateway":
        if state.fallback:
            return "gateway fallback SSE (preferred direct AIM failed)"
        if state.preferred_path == "gateway":
            return "gateway SSE (TF_PLAYGROUND_DIRECT_STREAM=0)"
        return "gateway SSE"
    if state.preferred_path == "direct-aim":
        return "preferred: direct AIM (pending)"
    return "preferred: gateway SSE"


def caption_line(state: RequestState) -> str:
    kind = (
        "content"
        if state.saw_content
        else "reasoning"
        if state.saw_reasoning
        else "stream"
    )
    if state.stream_path == "direct-aim":
        mode = (
            f"live AIM · route={state.route or '—'} · "
            f"classify={state.classify_ms if state.classify_ms is not None else '—'}ms"
        )
        if state.ttft_ms is not None:
            mode += f" · TTFT={state.ttft_ms}ms"
    elif state.gateway_buffered:
        mode = "paced (gateway-buffered SSE)"
        if state.fallback and state.fallback_reason:
            mode += " · fallback"
    else:
        mode = "gateway SSE"
        if state.fallback:
            mode += " · fallback"
    return (
        f"routed model={state.model or '—'} · finish={state.finish or '—'} · "
        f"{kind} · {mode}"
    )


def enrich_policy_from_metadata(
    ui_meta: dict[str, Any],
    route_name: str | None,
    endpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect honest policy fields from compiled metadata (no invented scores)."""
    rm = ui_meta.get("routing_matrix") or {}
    amd = ui_meta.get("amd_policy") or {}
    out: dict[str, Any] = {
        "active_profile": amd.get("active_profile")
        or ui_meta.get("policy_name")
        or rm.get("policy_name"),
        "objective_alias": rm.get("objective_alias")
        or amd.get("active_profile")
        or ui_meta.get("priority_mode"),
        "policy_version": amd.get("version") or rm.get("policy_version"),
        "routing_matrix": rm,
    }
    role = (endpoint or {}).get("role")
    out["use_case"] = guess_use_case(route_name, role)
    return out
