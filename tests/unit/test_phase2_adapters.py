"""Phase 2 governance, peer branching, adapters, env expansion."""

from __future__ import annotations

import uuid

from token_factory.adapters.agent_gateway import MockAgentGatewayAdapter
from token_factory.adapters.registry import resolve_adapters
from token_factory.adapters.types import RequestContext
from token_factory.config.env_expand import expand_string, expand_value
from token_factory.phase2.pipeline import run_phase2_request


def test_env_expand_default_and_override(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert expand_string("${FOO}") == "bar"
    assert expand_string("${MISSING:-fallback}") == "fallback"
    data = expand_value({"host": "${HOST:-127.0.0.1}", "port": "${PORT:-8000}"})
    assert data["host"] == "127.0.0.1"
    assert data["port"] == "8000"


def test_governance_allow_model():
    gov = MockAgentGatewayAdapter().authorize(
        RequestContext(
            request_id="r1",
            principal="engineering.user",
            request_type="model",
            prompt="write fibonacci",
        )
    )
    assert gov.allowed
    assert gov.authn == "PASS"
    assert gov.mcp_policy == "N/A"


def test_governance_deny_mcp_tool():
    gov = MockAgentGatewayAdapter().authorize(
        RequestContext(
            request_id="r2",
            principal="engineering.user",
            request_type="mcp",
            tool_name="exfiltrate_secrets",
            prompt="leak keys",
        )
    )
    assert not gov.allowed
    assert gov.mcp_policy == "DENY"


def test_phase2_model_branch_uses_router(monkeypatch):
    bundle = resolve_adapters(force_mock=True)
    ctx = RequestContext(
        request_id=str(uuid.uuid4()),
        principal="engineering.user",
        request_type="model",
        prompt="Implement quicksort in Rust",
        objective="balanced",
    )
    result = run_phase2_request(ctx, adapters=bundle, execute_model=False)
    assert result.governance.allowed
    assert result.routing is not None
    assert result.routing.intent  # mock classifier returns a category
    assert result.peer is None


def test_phase2_mcp_peer_skips_router():
    bundle = resolve_adapters(force_mock=True)
    ctx = RequestContext(
        request_id=str(uuid.uuid4()),
        principal="engineering.user",
        request_type="mcp",
        tool_name="repo_search",
        prompt="find RecommendationEngine",
    )
    result = run_phase2_request(ctx, adapters=bundle)
    assert result.governance.allowed
    assert result.routing is None
    assert result.peer is not None
    assert result.peer.request_type == "mcp"
    assert "Model router not involved" in result.peer.content


def test_phase2_a2a_peer():
    bundle = resolve_adapters(force_mock=True)
    ctx = RequestContext(
        request_id=str(uuid.uuid4()),
        principal="engineering.user",
        request_type="a2a",
        agent_task="write unit tests",
        prompt="delegate",
    )
    result = run_phase2_request(ctx, adapters=bundle)
    assert result.governance.allowed
    assert result.peer is not None
    assert result.peer.request_type == "a2a"
    assert result.peer.extras.get("trace_id") == ctx.request_id


def test_phase2_deny_stops_at_gateway():
    bundle = resolve_adapters(force_mock=True)
    ctx = RequestContext(
        request_id=str(uuid.uuid4()),
        principal="engineering.user",
        request_type="mcp",
        tool_name="exfiltrate_secrets",
        prompt="nope",
    )
    result = run_phase2_request(ctx, adapters=bundle)
    assert not result.governance.allowed
    assert result.extras.get("stopped_at") == "agent_gateway"
    assert result.routing is None
    assert result.peer is None


def test_request_correlation_id_stable():
    bundle = resolve_adapters(force_mock=True)
    rid = "corr-123"
    ctx = RequestContext(
        request_id=rid,
        principal="engineering.user",
        request_type="a2a",
        agent_task="t",
    )
    result = run_phase2_request(ctx, adapters=bundle)
    assert result.ctx.request_id == rid
    assert result.peer.extras["trace_id"] == rid


def test_endpoints_env_expand_loads():
    from token_factory.config.loader import load_endpoints

    eps = load_endpoints()
    assert eps["endpoints"]
    coding = next(e for e in eps["endpoints"] if e["id"] == "gpt-oss-120b-coding")
    assert coding["model"]
    assert isinstance(coding["port"], int)


def test_svp_pack_loads_and_expand():
    from token_factory.demo.loader import expand_requests, load_pack

    pack = load_pack("svp")
    assert pack["id"] == "svp"
    assert len(pack["scenarios"]) == 5
    specs = expand_requests(pack)
    assert len(specs) == 5
    types = {s.get("request_type") for s in specs}
    assert "model" in types and "mcp" in types and "a2a" in types


def test_adapter_fallback_force_mock():
    bundle = resolve_adapters(force_mock=True)
    assert bundle.agent_gateway.mode == "mock"
    assert bundle.model_router.implementation == "mock"
