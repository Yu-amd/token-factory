"""Phase 1 two-tier decisions and architecture verification honesty."""

from __future__ import annotations

from token_factory.phase1.decisions import (
    NOT_ENABLED,
    build_phase1_decisions,
    inspect_same_model_failover_configured,
)
from token_factory.phase1.verify import verify_phase1


def test_tier_decisions_never_fabricate_cache_or_auth():
    t1, t2 = build_phase1_decisions(
        model="openai/gpt-oss-120b",
        route="coding_route",
        classification="computer science",
        compute="instinct · MI300X",
        endpoint_id="gpt-oss-120b-coding",
        serving_pattern="interactive",
        health_latency_ms=42,
    )
    assert t1.provider == "on-prem-amd"
    assert t1.model == "openai/gpt-oss-120b"
    assert t1.auth == NOT_ENABLED
    assert t1.quota == NOT_ENABLED
    assert t2.kv_cache_aware == NOT_ENABLED
    assert t2.prefix_cache_aware == NOT_ENABLED
    assert t2.pd_disaggregation == NOT_ENABLED
    assert t2.cache_signal == NOT_ENABLED
    assert "not used for routing" in t2.load_signal
    assert t2.health_latency_ms == 42


def test_same_model_failover_detection():
    manifests = [
        {
            "kind": "AIGatewayRoute",
            "spec": {
                "rules": [
                    {
                        "backendRefs": [
                            {"name": "backend-a", "priority": 0},
                            {"name": "backend-b", "priority": 1},
                        ]
                    }
                ]
            },
        }
    ]
    assert inspect_same_model_failover_configured(manifests) is True
    assert inspect_same_model_failover_configured([]) is False


def test_verify_phase1_config_marks_unwired_features():
    report = verify_phase1(live=False)
    by_name = {c.name: c.status for c in report.checks}
    assert by_name["Rate limiting"] == "NOT ENABLED"
    assert by_name["Gateway auth enforcement"] == "NOT ENABLED"
    assert by_name["KV-cache-aware routing"] == "NOT ENABLED"
    assert by_name["Prefix-cache-aware routing"] == "NOT ENABLED"
    assert by_name["P/D disaggregation"] == "NOT ENABLED"
    assert by_name["Load-aware routing"] == "NOT ENABLED"
    assert by_name["Cross-model fallback"] == "NOT PROVEN"
    assert by_name["Tier-1 provider decision"] == "PASS"
    assert by_name["Tier-2 endpoint decision"] == "PASS"
    assert report.tier1 is not None and report.tier2 is not None
    assert report.tier1["auth"] == NOT_ENABLED
    assert report.tier2["kv_cache_aware"] == NOT_ENABLED
