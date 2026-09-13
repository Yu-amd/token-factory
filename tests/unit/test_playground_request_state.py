"""Unit tests for Playground request_state helpers."""

from __future__ import annotations

import sys
import time
from pathlib import Path

UI_ROOT = Path(__file__).resolve().parents[2] / "ui"
if str(UI_ROOT) not in sys.path:
    sys.path.insert(0, str(UI_ROOT))

from components.request_state import (
    apply_classify,
    apply_resolved_route,
    caption_line,
    elapsed_ms,
    enrich_policy_from_metadata,
    guess_use_case,
    mark_classifying,
    mark_complete,
    mark_failed,
    mark_fallback,
    mark_first_token,
    mark_streaming,
    new_request_state,
    stream_path_label,
)


def test_new_request_state_preferred_paths():
    assert new_request_state(direct_stream=True).preferred_path == "direct-aim"
    assert new_request_state(direct_stream=False).preferred_path == "gateway"


def test_classify_and_route_stage_progression():
    state = new_request_state(direct_stream=True)
    mark_classifying(state)
    assert state.stage == "classifying"
    assert state.nodes["router"].status == "active"

    classified = {
        "routing_decision": "coding_route",
        "classification": {"category": "coding_route", "confidence": 0.99},
        "matched_signals": {"domains": ["computer science"]},
        "recommended_model": "openai/gpt-oss-120b",
    }
    apply_classify(state, classified, classify_ms=120)
    assert state.classification == "coding_route"
    assert state.confidence == 0.99
    assert state.classify_ms == 120
    assert state.nodes["router"].status == "complete"
    assert state.stage == "resolving"

    apply_resolved_route(
        state,
        route_name="coding_route",
        model_id="openai/gpt-oss-120b",
        endpoint={"hardware": "instinct", "accelerator": "MI300X", "role": "coding"},
        policy_meta={"active_profile": "amd-balanced", "objective_alias": "balanced"},
        recommendation={
            "objective": "balanced",
            "serving_pattern": "interactive",
            "preference_label": "BALANCED_PREFERRED",
            "use_case": "coding-assistant",
        },
    )
    assert state.compute == "instinct · MI300X"
    assert state.serving_pattern == "interactive"
    assert state.nodes["policy"].status == "complete"
    assert state.nodes["aim"].status == "active"


def test_ttft_from_first_token_and_complete():
    state = new_request_state(direct_stream=True)
    mark_classifying(state)
    state.t0 = time.perf_counter() - 0.25
    mark_streaming(state, "direct-aim")
    state.stream_t0 = time.perf_counter() - 0.05
    mark_first_token(state, content=True)
    assert state.saw_content is True
    assert state.ttft_ms is not None
    assert state.ttft_ms >= 40
    assert "Streaming" in state.nodes["aim"].detail
    mark_complete(state)
    assert state.stage == "complete"
    assert state.total_ms is not None
    assert "live AIM" in caption_line(state)


def test_fallback_path_label_honesty():
    state = new_request_state(direct_stream=True)
    mark_fallback(state, "AIM HTTP 502")
    mark_streaming(state, "gateway")
    label = stream_path_label(state)
    assert "fallback" in label.lower()
    assert "gateway" in label.lower()
    state.gateway_buffered = True
    assert "fallback" in caption_line(state)


def test_failed_marks_active_node():
    state = new_request_state(direct_stream=True)
    mark_classifying(state)
    mark_failed(state, "boom")
    assert state.stage == "failed"
    assert any(n.status == "failed" for n in state.nodes.values())


def test_guess_use_case_and_enrich_metadata():
    assert guess_use_case("coding_route") == "coding-assistant"
    assert guess_use_case(None, "general") == "simple-chat"
    meta = {
        "policy_name": "amd-balanced",
        "routing_matrix": {"objective_alias": "balanced", "policy_version": "2.4"},
        "amd_policy": {"active_profile": "amd-balanced", "version": "2.4"},
    }
    out = enrich_policy_from_metadata(meta, "coding_route", {"role": "coding"})
    assert out["objective_alias"] == "balanced"
    assert out["use_case"] == "coding-assistant"


def test_elapsed_ms_none_safe():
    assert elapsed_ms(None) is None
    t0 = time.perf_counter() - 0.01
    assert elapsed_ms(t0) >= 5
