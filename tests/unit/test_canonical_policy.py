"""Tests for AMD Canonical Routing Policy consolidation."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from token_factory.config import load_policy_profile
from token_factory.policy import (
    PolicyValidationError,
    apply_profile_overlay,
    compile_effective_policy,
    explain_policy,
    list_profiles,
    load_canonical_policy,
    load_profile,
    policy_coverage,
    policy_ui_metadata,
    validate_canonical_policy,
)
from token_factory.policy.schema import validate_profile_overlay
from token_factory.routing_matrix import RecommendationEngine, load_routing_bundle

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_policy_loads_from_policies_path():
    policy = load_canonical_policy(ROOT)
    assert policy.get("_source_path", "").endswith("policies/amd-policy.yaml")
    meta = (policy.get("metadata") or {}).get("amd_routing_policy") or {}
    assert meta.get("version") == "2.4"
    assert policy.get("overrides")
    nested = policy.get("_canonical") or policy.get("policy") or {}
    assert nested.get("compute_positioning", {}).get("epyc", {}).get("statement")
    assert "not positioned as a replacement for GPU" in nested["compute_positioning"]["epyc"]["statement"]


def test_catalog_shim_redirects_to_canonical():
    bundle = load_routing_bundle(ROOT)
    assert bundle["policy"].get("overrides")
    assert (bundle["policy"].get("metadata") or {}).get("amd_routing_policy", {}).get(
        "version"
    ) == "2.4"


def test_schema_validation_ok():
    policy = load_canonical_policy(ROOT)
    bundle = load_routing_bundle(ROOT)
    errors = validate_canonical_policy(
        policy,
        use_case_ids={u["id"] for u in bundle["use_cases"]["use_cases"]},
        compute_ids={c["id"] for c in bundle["compute"]["compute"]},
        strict=False,
    )
    assert errors == []


def test_schema_validation_fails_on_bad_use_case_ref():
    policy = load_canonical_policy(ROOT)
    policy = deepcopy(policy)
    policy.setdefault("overrides", {})["not-a-real-use-case"] = {
        "m": {"MI300X": {"recommendation": "PREFERRED"}}
    }
    with pytest.raises(PolicyValidationError) as exc:
        validate_canonical_policy(
            policy,
            use_case_ids={"coding-assistant"},
            compute_ids={"MI300X"},
            strict=True,
        )
    assert any("unknown use-case" in e for e in exc.value.errors)


def test_schema_validation_fails_on_bad_compute_ref():
    policy = load_canonical_policy(ROOT)
    policy = deepcopy(policy)
    policy["overrides"] = {
        "coding-assistant": {
            "openai/gpt-oss-120b": {"NOT_A_GPU": {"recommendation": "PREFERRED"}}
        }
    }
    errors = validate_canonical_policy(
        policy,
        use_case_ids={"coding-assistant"},
        compute_ids={"MI300X"},
        strict=False,
    )
    assert any("unknown compute" in e for e in errors)


def test_profiles_are_overlays_not_full_matrices():
    profiles = list_profiles(ROOT)
    assert {p["id"] for p in profiles} >= {
        "amd-balanced",
        "amd-quality",
        "amd-cost-efficient",
        "amd-low-latency",
        "amd-edge-first",
        "amd-enterprise",
    }
    for p in profiles:
        doc = load_profile(p["id"], ROOT)
        errors = validate_profile_overlay(doc)
        assert errors == [], (p["id"], errors)
        overlay = doc.get("overlay") or {}
        assert "objective" in overlay or doc.get("policy", {}).get("priority_mode")
        assert "overrides" not in overlay
        assert "compute_positioning" not in overlay


def test_profile_overlay_changes_objective_not_eligibility():
    canonical = load_canonical_policy(ROOT)
    bal = apply_profile_overlay(canonical, "amd-balanced", root=ROOT)
    ent = apply_profile_overlay(canonical, "amd-enterprise", root=ROOT)
    assert bal.get("active_objective") == "balanced"
    assert ent.get("active_objective") == "enterprise"
    assert bal.get("overrides") == ent.get("overrides")
    assert (bal.get("_canonical") or {}).get("compute_positioning") == (
        ent.get("_canonical") or {}
    ).get("compute_positioning")


def test_backward_compat_load_policy_profile():
    for name in (
        "amd-balanced",
        "amd-quality",
        "amd-cost-efficient",
        "amd-low-latency",
        "amd-edge-first",
        "amd-enterprise",
    ):
        doc = load_policy_profile(name)
        assert doc["policy"]["name"] == name
        assert doc["policy"].get("routes")


def test_explain_matches_matrix_engine():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    explained = explain_policy(
        "coding-assistant",
        objective="balanced",
        serving_pattern="interactive",
        traffic="medium",
        lifecycle="production",
        engine=engine,
        endpoints=[],
    )
    matrix = engine.recommend(
        "coding-assistant",
        objective="balanced",
        serving_pattern="interactive",
        utilization="medium",
        lifecycle_mode="production",
        endpoints=[],
    )
    assert explained["steps"][0]["step"] == 1
    assert len(explained["steps"]) == 7
    exp_top = (explained.get("amd_recommendation") or [None])[0]
    mat_top = (matrix.get("ranked") or [None])[0]
    assert exp_top and mat_top
    assert exp_top["model"] == mat_top["model"]
    assert exp_top["compute"] == mat_top["compute"]


def test_perf_balance_lcs_can_diverge():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cards = engine.summary_cards(
        "enterprise-chat",
        lifecycle_mode="production",
        serving_pattern="interactive",
        utilization="high",
    )["cards"]
    perf = cards["best_performance"]["candidate"]
    bal = cards["best_balance"]["candidate"]
    lcs = cards["lowest_cost_sufficient"]["candidate"]
    # At least one pair diverges (model or compute)
    diverged = (
        (perf["model"], perf["compute"]) != (bal["model"], bal["compute"])
        or (perf["model"], perf["compute"]) != (lcs["model"], lcs["compute"])
        or (bal["model"], bal["compute"]) != (lcs["model"], lcs["compute"])
    )
    assert diverged
    assert cards["best_balance"].get("why_not_performance")


def test_epyc_rises_batch_not_interactive():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    batch_cards = engine.summary_cards(
        "batch-summarization",
        serving_pattern="batch",
        utilization="low",
        lifecycle_mode="production",
    )
    assert batch_cards["cards"]["best_batch"]["candidate"]["family"] == "epyc"
    interactive = engine.recommend(
        "enterprise-chat",
        objective="enterprise",
        serving_pattern="interactive",
        utilization="high",
        lifecycle_mode="production",
    )
    assert interactive["ranked"][0]["family"] != "epyc"

def test_radeon_local_first_and_vlm_gates():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    local = engine.recommend(
        "vlm",
        objective="edge-local",
        serving_pattern="interactive",
        lifecycle_mode="production-preview",
        data_locality=True,
    )
    assert local["ranked"]
    for c in local["candidates"]:
        caps = engine.models[c["model"]]["capabilities"]
        assert caps.get("vision") is True
    # Local-first should surface Radeon among top when Preview allowed
    families = {c["family"] for c in local["ranked"][:6]}
    assert "radeon" in families or any(c["compute"] in ("R9700", "W7900") for c in local["ranked"][:8])


def test_mi350p_tech_preview_gated():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    prod = engine.recommend(
        "enterprise-chat", objective="balanced", lifecycle_mode="production"
    )
    ev = engine.recommend(
        "enterprise-chat", objective="balanced", lifecycle_mode="evaluation"
    )
    assert not any(c["compute"] == "MI350P" for c in prod["ranked"])
    assert any(c["compute"] == "MI350P" for c in ev["ranked"]) or any(
        c["compute"] == "MI350P" for c in (ev.get("lifecycle_exclusions") or [])
    ) or any(c["compute"] == "MI350P" for c in ev["candidates"])


def test_coverage_every_use_case_has_path_or_gap():
    result = policy_coverage(engine=RecommendationEngine(load_routing_bundle(ROOT)))
    assert result["counts"]["use_cases"] == len(result["use_cases"])
    for row in result["use_cases"]:
        assert row["status"] in {
            "ga-capable",
            "preview-only",
            "tech-preview-only",
            "no-eligible-candidate",
        }
        if row["status"] == "no-eligible-candidate":
            assert row.get("gap")
        else:
            # At least one lifecycle path non-empty
            assert any(row["paths"].get(k) for k in ("production", "production-preview", "evaluation"))


def test_ui_metadata_represents_canonical_policy():
    meta = policy_ui_metadata(profile_name="amd-balanced")
    assert meta["version"] == "2.4"
    assert meta["eligibility_rules"]
    assert meta["compute_positioning"]["instinct"]["statement"]
    assert meta["serving_patterns"]["interactive"]
    assert meta["coverage"]["counts"]["use_cases"] >= 1
    assert meta["compiled_routes"] is not None
    assert "CAN RUN" in (meta["canonical_vs_runtime"]["aim_catalog"]["role"])


def test_runtime_routes_explainable():
    compiled = compile_effective_policy(profile_name="amd-balanced")
    routes = compiled["compiled_runtime_routes"]
    assert routes
    for r in routes:
        assert "explainable_by" in r
        assert r.get("name")


def test_compute_positioning_statements_exact_intent():
    nested = load_canonical_policy(ROOT).get("_canonical") or {}
    pos = nested["compute_positioning"]
    assert "primary AMD compute class" in pos["instinct"]["statement"]
    assert "PCIe enterprise" in pos["mi350p"]["statement"]
    assert "lifecycle-gated" in pos["mi350p"]["statement"]
    assert "local/workstation" in pos["radeon"]["statement"]
    assert "CPU-centric" in pos["epyc"]["statement"]
    assert pos["continuum_label"] == "Deployment positioning — not a benchmark ranking"
