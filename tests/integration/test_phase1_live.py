"""Phase 1 live path: gateway → classify → model → MI300X.

Skipped unless TF_PHASE1_LIVE=1 (or pytest -m live with env set).
"""

from __future__ import annotations

import os

import pytest

from token_factory.phase1.verify import verify_phase1

pytestmark = pytest.mark.skipif(
    os.environ.get("TF_PHASE1_LIVE", "").lower() not in ("1", "true", "yes"),
    reason="Set TF_PHASE1_LIVE=1 to run live Phase 1 gateway→MI300X checks",
)


def test_phase1_live_gateway_to_mi300x():
    report = verify_phase1(live=True)
    by_name = {c.name: c for c in report.checks}

    assert by_name["Envoy AI Gateway"].status == "PASS"
    assert by_name["vLLM Semantic Router"].status == "PASS"
    assert by_name["Semantic classification"].status == "PASS"
    assert by_name["Model selection"].status == "PASS"
    assert by_name["Live MI300X endpoint"].status == "PASS"
    assert by_name["Gateway → MI300X response"].status == "PASS"

    # Honesty: unwired Tier-2 features must not claim PASS
    assert by_name["KV-cache-aware routing"].status == "NOT ENABLED"
    assert by_name["Prefix-cache-aware routing"].status == "NOT ENABLED"
    assert by_name["P/D disaggregation"].status == "NOT ENABLED"
    assert by_name["Rate limiting"].status == "NOT ENABLED"
    assert by_name["Cross-model fallback"].status == "NOT PROVEN"

    assert report.tier1 is not None
    assert report.tier2 is not None
    assert report.tier1.get("model")
    assert report.tier2.get("endpoint")
    assert report.overall.startswith("PASS")
