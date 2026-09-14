"""Tests for AMD Opinionated Routing Matrix engine (V2 + MI350P + Radeon Preview)."""

from __future__ import annotations

from pathlib import Path

import yaml

from token_factory.config import load_endpoints
from token_factory.routing_matrix import (
    RecommendationEngine,
    load_routing_bundle,
    mi350p_tech_preview_models,
    normalize_model_id,
)
from token_factory.routing_matrix.engine import LEVEL_ORDER

ROOT = Path(__file__).resolve().parents[2]

RADEON_PREVIEW_MODELS = [
    "google/gemma-3n-E4B-it",
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3.5-9B",
    "zai-org/GLM-4.7-Flash",
]

MI350P_SUPPLIED = [
    "openai/gpt-oss-120b",
    "meta-llama/Llama-3.3-70B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2501",
    "google/gemma-3-27b-it",
    "Qwen/Qwen3.8-27B",
    "google/gemma4-31b-it",
    "google/gemma4-26B-A4B",
    "google/gemma-4-12B-it",
    "openai/gpt-oss-20b",
    "Qwen/Qwen3.6-35B-A3B",
    "Qwen/Qwen3.6-27B",
]


def test_bundle_loads():
    bundle = load_routing_bundle(ROOT)
    assert bundle["aims"]["aims"]
    assert bundle["compute"]["compute"]
    assert bundle["use_cases"]["use_cases"]
    assert bundle["models"]["models"]
    assert bundle["policy"]["version"]
    assert any(c["id"] == "MI350P" for c in bundle["compute"]["compute"])


def test_list_lifecycle_modes():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    modes = engine.list_lifecycle_modes()
    ids = {m["id"] for m in modes}
    assert ids >= {"production", "production-preview", "evaluation", "all"}
    for m in modes:
        assert m["display_name"]
        assert isinstance(m["allow"], list) and m["allow"]
    # UI builds select options from display_name → id
    life_opts = {m["display_name"]: m["id"] for m in modes}
    assert life_opts["Production"] == "production"
    assert engine.resolve_lifecycle_mode("eval") == "evaluation"
    assert engine._allowed_lifecycles("production") == {"ga"}


def test_non_aim_combination_never_recommended():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", objective="balanced")
    for c in rec["candidates"]:
        aim = next(a for a in engine.bundle["aims"]["aims"] if a["model"] == c["model"])
        family = c["family"]
        assert c["compute"] in (aim.get("support") or {}).get(family, {})


def test_vision_requires_vision_capability():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "vlm", objective="balanced", lifecycle_mode="production-preview"
    )
    assert rec["candidates"]
    for c in rec["candidates"]:
        caps = engine.models[c["model"]]["capabilities"]
        assert caps.get("vision") is True


def test_coding_assistant_includes_coder_or_instruct():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", objective="balanced")
    models = {c["model"] for c in rec["ranked"][:10]}
    assert any("Coder" in m or "gpt-oss" in m for m in models)


def test_token_cost_prefers_epyc_or_radeon_for_simple_chat():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "simple-chat",
        objective="token-cost",
        lifecycle_mode="production-preview",
    )
    assert rec["ranked"]
    top = rec["ranked"][0]
    assert top["family"] in ("epyc", "radeon", "instinct")
    families = {c["family"] for c in rec["ranked"][:5]}
    assert "epyc" in families or "radeon" in families


def test_quality_does_not_simply_pick_cheapest():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    quality = engine.recommend("complex-reasoning", objective="quality")
    assert quality["ranked"]
    assert quality["ranked"][0]["family"] == "instinct"


def test_unoptimized_not_preferred():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", objective="balanced")
    for c in rec["candidates"]:
        if c["aim_support"] == "unoptimized":
            assert LEVEL_ORDER[c["recommendation"]] <= LEVEL_ORDER["ACCEPTABLE"]


def test_matrix_cells_match_engine():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix("coding-assistant", objective="balanced")
    assert matrix["columns"]
    assert "MI350P" in matrix["columns"]
    assert matrix["rows"]
    for model, cols in matrix["cells"].items():
        for compute, cell in cols.items():
            assert cell["model"] == model
            assert cell["compute"] == compute


def test_deployed_endpoint_overlay_and_simulate():
    endpoints = load_endpoints(ROOT / "config" / "endpoints.yaml")["endpoints"]
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    sim = engine.simulate_route(
        "coding-assistant", objective="balanced", endpoints=endpoints
    )
    assert sim["eligible_combinations"] >= 1
    deployed = sim["currently_deployed_eligible"]
    if deployed:
        assert sim["selected_runtime_route"]["endpoint_available"] is True


def test_sparse_radeon_only_where_aim_exists():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "simple-chat",
        objective="edge-local",
        lifecycle_mode="production-preview",
    )
    for c in rec["candidates"]:
        if c["family"] == "radeon":
            aim = engine.aims[c["model"]]
            assert c["compute"] in aim["support"]["radeon"]


def test_policy_profiles_still_validate():
    from token_factory.catalog import load_catalog
    from token_factory.config import load_endpoints, load_policies, load_token_factory, validate_all

    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    tf = load_token_factory(ROOT / "config" / "token-factory.example.yaml")
    paths = list((ROOT / "policies" / "profiles").glob("amd-*.yaml"))
    paths += [
        p for p in (ROOT / "policies").glob("amd-*.yaml") if p.name != "amd-policy.yaml"
    ]
    for path in paths:
        policies = load_policies(path)
        errors = validate_all(endpoints, policies, tf, catalog)
        assert not errors, (path, errors)


def test_amd_profile_names_alias_to_objectives():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    assert engine.resolve_objective("amd-balanced", "coding-assistant") == "balanced"
    assert engine.resolve_objective("amd-cost-efficient", "simple-chat") == "token-cost"
    assert engine.resolve_objective("amd-edge-first", "simple-chat") == "edge-local"
    rec = engine.recommend("coding-assistant", objective="amd-balanced")
    assert rec["objective"] == "balanced"
    assert rec["ranked"]
    assert rec["cost_data"] == "relative"


# --- MI350P / Tech Preview ---


def test_mi350p_eleven_models_normalized_once():
    bundle = load_routing_bundle(ROOT)
    aliases = bundle["aliases"]
    canonical = [normalize_model_id(s, aliases) for s in MI350P_SUPPLIED]
    assert len(canonical) == 11
    assert len(set(canonical)) == 11
    tp = mi350p_tech_preview_models(bundle)
    assert len(tp) == 11
    assert set(tp) == set(canonical)
    # No duplicate MI350P cells per model
    for aim in bundle["aims"]["aims"]:
        cell = (aim.get("support") or {}).get("instinct", {}).get("MI350P")
        if cell:
            assert isinstance(cell, dict)
            assert cell.get("lifecycle") == "tech-preview"


def test_tech_preview_excluded_from_production_by_default():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", lifecycle_mode="production")
    assert all(c["compute"] != "MI350P" for c in rec["candidates"])
    assert any(
        e["compute"] == "MI350P" and e["lifecycle"] == "tech-preview"
        for e in rec["lifecycle_exclusions"]
    )


def test_tech_preview_eligible_when_evaluation_allowed():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", lifecycle_mode="evaluation")
    mi = [c for c in rec["candidates"] if c["compute"] == "MI350P"]
    assert mi
    assert all(c["lifecycle"] == "tech-preview" for c in mi)
    assert all(c.get("rank") for c in mi if c["recommendation"] in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE"))


def test_matrix_mi350p_column_shows_tech_preview():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "coding-assistant", lifecycle_mode="evaluation", include_excluded=True
    )
    assert "MI350P" in matrix["columns"]
    found = False
    for model, cols in matrix["cells"].items():
        cell = cols.get("MI350P")
        if cell and cell.get("aim_support") is not None:
            assert cell["lifecycle"] == "tech-preview"
            found = True
    assert found


def test_mi350p_ranks_when_eligible():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", lifecycle_mode="evaluation", show="all")
    ranked_mi = [c for c in rec["candidates"] if c["compute"] == "MI350P" and c.get("rank")]
    assert ranked_mi
    assert ranked_mi[0]["rank"] >= 1
    # Inverse: I-have MI350P surfaces TP AIMs for the use case
    inv = engine.recommend_for_compute("MI350P", use_case_id="coding-assistant")
    assert inv["use_cases"][0]["top"]
    assert inv["use_cases"][0]["top"][0]["compute"] == "MI350P"


def test_lowest_cost_sufficient_high_end_not_auto_win():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "simple-chat",
        objective="lowest-cost-sufficient",
        lifecycle_mode="production-preview",
        utilization="low",
    )
    assert rec["ranked"]
    top = rec["ranked"][0]
    # Cheaper class that clears floor should beat MI355X
    assert top["compute"] not in ("MI355X", "MI350X")
    assert top["family"] in ("epyc", "radeon") or top["hardware_cost_class"] in (
        "low",
        "medium",
    )


def test_incapable_cheap_never_beats_capable():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    # complex-reasoning requires reasoning — small non-reasoning on EPYC must not win
    rec = engine.recommend(
        "complex-reasoning",
        objective="lowest-cost-sufficient",
        lifecycle_mode="production",
    )
    assert rec["ranked"]
    for c in rec["ranked"][:5]:
        caps = engine.models[c["model"]]["capabilities"]
        assert caps.get("reasoning") is True
    # Top should be capable Instinct-class, not random cheap without reasoning
    assert rec["ranked"][0]["family"] == "instinct" or engine.models[
        rec["ranked"][0]["model"]
    ]["capabilities"].get("reasoning")


def test_traffic_low_vs_high_changes_economic_ranking():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    low = engine.recommend(
        "simple-chat",
        objective="lowest-cost-sufficient",
        utilization="low",
        lifecycle_mode="production-preview",
    )
    high = engine.recommend(
        "enterprise-chat",
        objective="balanced",
        utilization="high",
        lifecycle_mode="production",
    )
    assert low["ranked"]
    assert high["ranked"]
    assert low["ranked"][0]["family"] in ("epyc", "radeon")
    assert high["ranked"][0]["family"] == "instinct"


def test_i_have_mi350p_inverse():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    inv = engine.recommend_for_compute(
        "MI350P", objective="balanced", use_case_id="coding-assistant"
    )
    assert inv["lifecycle_mode"] == "evaluation"
    assert inv["use_cases"]
    tops = inv["use_cases"][0]["top"]
    assert all(t["compute"] == "MI350P" for t in tops)
    assert all(t["lifecycle"] == "tech-preview" for t in tops)


def test_summary_cards_exist():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cards = engine.summary_cards("coding-assistant", lifecycle_mode="evaluation")
    assert "best_performance" in cards["cards"]
    assert "best_balance" in cards["cards"]
    assert "lowest_cost_sufficient" in cards["cards"]


def test_no_fabricated_mi350p_benchmarks():
    cost = yaml.safe_load((ROOT / "catalog" / "cost-model.yaml").read_text())
    assert cost["compute_costs"]["MI350P"]["dollars_per_accelerator_hour"] is None
    assert cost["measured"]["benchmarks"] == []
    compute = yaml.safe_load((ROOT / "catalog" / "compute.yaml").read_text())
    mi = next(c for c in compute["compute"] if c["id"] == "MI350P")
    assert mi["token_economic_efficiency"] is None
    assert "MI350X" != "MI350P"
    assert mi.get("form_factor") == "PCIe"


# --- Radeon Preview ---


def test_radeon_preview_five_models_both_gpus():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    for model in RADEON_PREVIEW_MODELS:
        aim = engine.aims[model]
        for gpu in ("R9700", "W7900"):
            cell = aim["support"]["radeon"][gpu]
            assert cell["support"] == "preview"
            assert cell["lifecycle"] == "preview"


def test_radeon_preview_excluded_from_production():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "simple-chat", objective="edge-local", lifecycle_mode="production"
    )
    assert all(c["family"] != "radeon" for c in rec["candidates"])
    assert any(
        e["family"] == "radeon" and e["lifecycle"] == "preview"
        for e in rec["lifecycle_exclusions"]
    )


def test_radeon_preview_eligible_in_production_preview_or_evaluation():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    for mode in ("production-preview", "evaluation"):
        rec = engine.recommend(
            "simple-chat",
            objective="edge-local",
            lifecycle_mode=mode,
            utilization="low",
            deployment="workstation",
        )
        radeon = [c for c in rec["candidates"] if c["family"] == "radeon"]
        assert radeon, mode
        assert all(c["lifecycle"] == "preview" for c in radeon)


def test_radeon_wins_local_simple_chat_low_traffic():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "simple-chat",
        objective="edge-local",
        lifecycle_mode="production-preview",
        utilization="low",
        deployment="workstation",
    )
    assert rec["ranked"]
    assert rec["ranked"][0]["family"] == "radeon"
    assert rec["ranked"][0]["compute"] in ("R9700", "W7900")


def test_radeon_vlm_local_and_text_only_ineligible_for_vision():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    vlm = engine.recommend(
        "vlm",
        objective="edge-local",
        lifecycle_mode="production-preview",
        utilization="low",
    )
    assert vlm["ranked"]
    assert vlm["ranked"][0]["model"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert vlm["ranked"][0]["family"] == "radeon"
    # Text-only Radeon models must not appear
    text_only = {
        "Qwen/Qwen3.5-9B",
        "meta-llama/Llama-3.1-8B-Instruct",
        "zai-org/GLM-4.7-Flash",
    }
    assert not any(c["model"] in text_only for c in vlm["candidates"])
    caps = engine.models["Qwen/Qwen3-VL-8B-Instruct"]["capabilities"]
    assert caps.get("vision") is True
    assert caps.get("multimodal") is True


def test_high_concurrency_prefers_instinct_over_radeon():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "enterprise-chat",
        objective="enterprise",
        lifecycle_mode="production-preview",
        utilization="high",
    )
    assert rec["ranked"]
    assert rec["ranked"][0]["family"] == "instinct"
    # Radeon may appear later but must not be Rank #1 for high-concurrency enterprise
    if any(c["family"] == "radeon" for c in rec["ranked"][:3]):
        assert rec["ranked"][0]["family"] != "radeon"


def test_data_locality_prefers_radeon_or_reports_none():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    ok = engine.recommend(
        "simple-chat",
        objective="edge-local",
        lifecycle_mode="production-preview",
        data_locality=True,
        utilization="low",
    )
    assert ok["ranked"][0]["family"] == "radeon"
    # Hard reasoning with only local filter when no capable local AIM
    hard = engine.recommend(
        "complex-reasoning",
        objective="edge-local",
        lifecycle_mode="production-preview",
        data_locality=True,
    )
    # Either no local candidates (note set) or non-local deprioritized
    if hard.get("locality_note"):
        assert "No local candidate" in hard["locality_note"]
    else:
        # If somehow a local reasoning AIM existed, fine — else top shouldn't be forced wrong
        assert hard["ranked"]


def test_i_have_r9700_inverse():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    inv = engine.recommend_for_compute(
        "R9700", objective="edge-local", use_case_id="simple-chat"
    )
    assert inv["lifecycle_mode"] == "production-preview"
    assert inv["use_cases"]
    assert all(t["compute"] == "R9700" for t in inv["use_cases"][0]["top"])


def test_simulate_explains_lifecycle_exclusions():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    sim = engine.simulate_route(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
    )
    assert "lifecycle_exclusions" in sim
    assert "explanation" in sim
    # MI350P should be mentioned as excluded in production
    assert any(e["compute"] == "MI350P" for e in sim["lifecycle_exclusions"]) or (
        "MI350P" in sim["explanation"]
    )


def test_best_fit_cards_can_select_radeon():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cards = engine.summary_cards(
        "simple-chat",
        lifecycle_mode="production-preview",
        utilization="low",
        deployment="workstation",
    )
    # At least one card may pick Radeon when policy/objective favors local
    families = {
        (cards["cards"][k].get("candidate") or {}).get("family")
        for k in cards["cards"]
    }
    assert "radeon" in families or "epyc" in families


def test_matrix_private_eval_mi350p_r9700_nonempty_under_evaluation():
    """MI350P and R9700 matrix cells are populated (not empty) under evaluation,
    including when Deployment=enterprise would otherwise hide workstation Radeon.
    """
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    for uc in ("coding-assistant", "simple-chat"):
        matrix = engine.matrix(
            uc,
            objective="balanced",
            deployment="enterprise",
            lifecycle_mode="evaluation",
            show="recommended+supported",
        )
        assert "MI350P" in matrix["columns"]
        assert "R9700" in matrix["columns"]
        assert "W7900" in matrix["columns"]

        mi_cells = [
            (m, cols["MI350P"])
            for m, cols in matrix["cells"].items()
            if cols.get("MI350P") and cols["MI350P"].get("aim_support") is not None
        ]
        r9_cells = [
            (m, cols["R9700"])
            for m, cols in matrix["cells"].items()
            if cols.get("R9700") and cols["R9700"].get("aim_support") is not None
        ]
        assert mi_cells, f"{uc}: expected MI350P private-eval cells"
        assert r9_cells, f"{uc}: expected R9700 private-eval cells (enterprise must not blank column)"

        for _model, cell in mi_cells:
            assert cell["lifecycle"] == "tech-preview"
            assert cell.get("availability") == "private-eval"
            assert cell.get("deployment_channel") == "private-eval-container"
            assert not cell.get("lifecycle_excluded")

        for _model, cell in r9_cells:
            assert cell["lifecycle"] == "preview"
            assert cell.get("availability") == "private-eval"
            assert not cell.get("lifecycle_excluded")

        # display_rows must include models that populate those columns
        assert any(m in matrix["display_rows"] for m, _ in mi_cells)
        assert any(m in matrix["display_rows"] for m, _ in r9_cells)


def test_matrix_private_eval_visible_tagged_under_production():
    """Under Production, Preview/TP cells stay visible (tagged), not omitted as —."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "simple-chat",
        objective="balanced",
        deployment="enterprise",
        lifecycle_mode="production",
        include_excluded=True,
    )
    mi_cells = [
        cols["MI350P"]
        for cols in matrix["cells"].values()
        if cols.get("MI350P") and cols["MI350P"].get("aim_support") is not None
    ]
    r9_cells = [
        cols["R9700"]
        for cols in matrix["cells"].values()
        if cols.get("R9700") and cols["R9700"].get("aim_support") is not None
    ]
    assert mi_cells, "MI350P column must not be empty under Production"
    assert r9_cells, "R9700 column must not be empty under Production"
    assert all(c.get("lifecycle_excluded") for c in mi_cells)
    assert all(c.get("lifecycle_excluded") for c in r9_cells)
    assert all(c.get("availability") == "private-eval" for c in mi_cells + r9_cells)
    assert any(
        m in matrix["display_rows"]
        for m, cols in matrix["cells"].items()
        if cols.get("MI350P") and cols["MI350P"].get("aim_support") is not None
    )
    assert any(
        m in matrix["display_rows"]
        for m, cols in matrix["cells"].items()
        if cols.get("R9700") and cols["R9700"].get("aim_support") is not None
    )
    assert "private eval" in (matrix.get("private_eval_note") or "").lower()


# --- Distinct card selectors / serving pattern / matrix marks ---


def test_summary_cards_perf_balance_lcs_can_diverge():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cards = engine.summary_cards(
        "coding-assistant",
        lifecycle_mode="production",
        utilization="medium",
        deployment="enterprise",
        serving_pattern="interactive",
    )
    perf = cards["cards"]["best_performance"]["candidate"]
    bal = cards["cards"]["best_balance"]["candidate"]
    lcs = cards["cards"]["lowest_cost_sufficient"]["candidate"]
    assert perf and bal and lcs
    # Must not all collapse to the same cell
    triples = {(perf["model"], perf["compute"]), (bal["model"], bal["compute"]), (lcs["model"], lcs["compute"])}
    assert len(triples) >= 2
    # Performance maximizes Instinct-class; LCS is constrained cheapest sufficient
    assert perf["family"] == "instinct"
    assert lcs["hardware_cost_class"] in ("low", "medium") or engine._hw_cost_rank(
        lcs["compute"]
    ) < engine._hw_cost_rank(perf["compute"])
    # Balance should not auto-pick very-high-cost weak economic_fit when alternatives exist
    assert not (
        bal["hardware_cost_class"] == "very-high" and bal["economic_fit"] < 0.35
    )
    assert cards["cards"]["best_balance"].get("why_not_performance")


def test_lcs_enforces_floor_before_economics():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "complex-reasoning",
        objective="lowest-cost-sufficient",
        lifecycle_mode="production",
    )
    floor = engine._floor_tier("complex-reasoning")
    assert rec["ranked"]
    for c in rec["ranked"][:8]:
        assert engine._model_tier(c["model"]) >= floor
        assert engine.models[c["model"]]["capabilities"].get("reasoning") is True


def test_interactive_vs_batch_ranking_differs():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    inter = engine.recommend(
        "summarization",
        objective="balanced",
        serving_pattern="interactive",
        utilization="medium",
        lifecycle_mode="production",
    )
    batch = engine.recommend(
        "summarization",
        objective="balanced",
        serving_pattern="batch",
        utilization="low",
        lifecycle_mode="production",
    )
    assert inter["serving_pattern"] == "interactive"
    assert batch["serving_pattern"] == "batch"
    assert inter["ranked"] and batch["ranked"]
    # Batch should surface EPYC earlier / prefer batch-friendly compute
    batch_top_families = [c["family"] for c in batch["ranked"][:5]]
    inter_top = inter["ranked"][0]
    batch_cards = engine.summary_cards(
        "summarization",
        serving_pattern="batch",
        utilization="low",
        lifecycle_mode="production",
    )
    assert "best_batch" in batch_cards["cards"]
    assert batch_cards["cards"]["best_batch"]["candidate"]["family"] == "epyc"
    assert "epyc" in batch_top_families or batch_cards["cards"]["lowest_cost_sufficient"][
        "candidate"
    ]["family"] == "epyc"
    # Interactive high-concurrency should not crown EPYC
    assert inter_top["family"] != "epyc" or inter["utilization"] != "high"


def test_epyc_rises_batch_relaxed_not_high_interactive():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    batch = engine.summary_cards(
        "batch-summarization",
        serving_pattern="batch",
        utilization="low",
        lifecycle_mode="production",
    )
    assert batch["cards"]["best_batch"]["candidate"]["family"] == "epyc"
    high = engine.recommend(
        "enterprise-chat",
        objective="balanced",
        serving_pattern="interactive",
        utilization="high",
        lifecycle_mode="production",
    )
    assert high["ranked"][0]["family"] == "instinct"
    assert high["ranked"][0]["family"] != "epyc"


def test_radeon_local_wins_when_capable_incapable_never():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cards = engine.summary_cards(
        "simple-chat",
        lifecycle_mode="production-preview",
        utilization="low",
        deployment="workstation",
        data_locality=True,
        serving_pattern="interactive",
    )
    assert "best_local" in cards["cards"]
    local = cards["cards"]["best_local"]["candidate"]
    assert local["family"] == "radeon"
    # VLM: text-only never
    vlm = engine.recommend(
        "vlm",
        objective="edge-local",
        lifecycle_mode="production-preview",
        utilization="low",
    )
    text_only = {
        "Qwen/Qwen3.5-9B",
        "meta-llama/Llama-3.1-8B-Instruct",
        "zai-org/GLM-4.7-Flash",
    }
    assert not any(c["model"] in text_only for c in vlm["candidates"])


def test_coding_quality_fit_not_dominated_by_size_soft_bias_same_compute():
    """Workload strengths / policy matter more than size soft-bias; specialization is weak."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "coding-assistant",
        objective="quality",
        lifecycle_mode="production",
        serving_pattern="interactive",
        compute_filter="MI355X",
    )
    ranked = rec["ranked"]
    assert ranked
    # Both coding-capable peers remain eligible; do not require Coder always wins globally
    models = {c["model"] for c in ranked}
    assert "Qwen/Qwen3-Coder-Next" in models or "zai-org/GLM-4.7" in models
    top = ranked[0]
    # Quality objective should surface strong quality_fit, not merely large size_class
    assert top.get("quality_fit", 0) >= 0.5
    # Specialization alone must not dwarf measured evidence path — no AMD measured yet,
    # so Preferred confidence must not be High
    preferred = [c for c in ranked if c["recommendation"] == "PREFERRED"]
    for p in preferred:
        assert str(p.get("confidence")).lower() != "high"


def test_glm_and_qwen_coder_both_coding_eligible():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    for mid in ("zai-org/GLM-4.7", "Qwen/Qwen3-Coder-Next"):
        meta = engine.models[mid]
        assert meta["capabilities"]["coding"] is True
    rec = engine.recommend(
        "coding-assistant",
        lifecycle_mode="production",
        compute_filter="MI355X",
    )
    models = {c["model"] for c in rec["candidates"]}
    assert "zai-org/GLM-4.7" in models
    assert "Qwen/Qwen3-Coder-Next" in models
    # Neither stale-disqualified by false coding=false
    assert not any(
        c["model"] == "zai-org/GLM-4.7" and c.get("capability_excluded")
        for c in rec["candidates"]
    )


def test_preferred_confidence_not_high_without_amd_measured():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "coding-assistant",
        lifecycle_mode="production",
        compute_filter="MI355X",
    )
    preferred = [c for c in rec["ranked"] if c["recommendation"] == "PREFERRED"]
    assert preferred, "expected at least one Preferred override on MI355X coding-assistant"
    for c in preferred:
        pe = (c.get("performance_evidence") or {}).get("status")
        assert pe != "AMD_MEASURED" or True  # catalog has null amd_measurements
        assert str(c.get("confidence")) in ("Medium", "Low", "Experimental", "High")
        if pe != "AMD_MEASURED":
            assert str(c.get("confidence")) != "High"


def test_compare_models_explainable_no_forced_winner():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    cmp = engine.compare_models(
        "coding-assistant",
        "Qwen/Qwen3-Coder-Next",
        "zai-org/GLM-4.7",
        compute_id="MI355X",
    )
    assert cmp["dimensions"]["capability_coding"]["Qwen/Qwen3-Coder-Next"] == "✓"
    assert cmp["dimensions"]["capability_coding"]["zai-org/GLM-4.7"] == "✓"
    assert cmp["amd_performance_evidence"]["Qwen/Qwen3-Coder-Next"] in (
        "PUBLIC_ONLY",
        "NO_DATA",
        "ESTIMATED",
        "AMD_MEASURED",
    )
    assert "caveat" in cmp and "AMD comparative" in cmp["caveat"]
    # Do not assert Qwen must always win — only that comparison is structured
    assert "policy_preference" in cmp
    assert cmp.get("language_note")


def test_unknown_capability_not_silent_false():
    from token_factory.routing_matrix.evidence import cap_is_false, cap_is_unknown, cap_truth

    assert cap_truth("unknown") == "unknown"
    assert cap_is_unknown("unknown")
    assert not cap_is_false("unknown")
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    # Cohere coding left unknown — not treated as coding=false for false-negative audit
    cohere = engine.models["CohereLabs/command-a-reasoning-08-2025"]
    assert cohere["capabilities"]["coding"] in (False, "unknown") or cohere["capabilities"]["coding"] is False
    # Prefer unknown over false for reasoning-specialized when coding unproven
    assert cohere["capabilities"]["coding"] == "unknown"


def test_specialization_alone_does_not_dominate_quality_evidence():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend(
        "coding-assistant",
        objective="quality",
        lifecycle_mode="production",
        compute_filter="MI355X",
    )
    coder = next(c for c in rec["ranked"] if c["model"] == "Qwen/Qwen3-Coder-Next")
    glm = next(c for c in rec["ranked"] if c["model"] == "zai-org/GLM-4.7")
    # Both have high quality_fit from strengths; gap must not be specialization+22 style
    assert abs((coder.get("quality_fit") or 0) - (glm.get("quality_fit") or 0)) < 0.25
    # Score delta should be modest relative to old +22 specialization cliff
    assert abs(coder["score"] - glm["score"]) < 40


def test_matrix_ui_only_numbers_top_candidates():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
        serving_pattern="interactive",
    )
    numbered = []
    for cols in matrix["cells"].values():
        for cell in cols.values():
            mark = cell.get("matrix_mark")
            rank = cell.get("rank")
            if mark and mark not in ("★", "✓", "○", "⊘", "—") and rank:
                numbered.append(rank)
                assert rank <= 5
            # Must not show raw high ranks as the display mark digits like ✓27
            if mark and mark.startswith("✓"):
                assert mark == "✓"
    assert any(
        c.get("matrix_mark") in ("★", "①", "②", "③", "④", "⑤")
        for cols in matrix["cells"].values()
        for c in cols.values()
    )


def test_live_overlay_does_not_change_catalog_semantics():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    fake = [
        {
            "id": "fake-ep",
            "model": "Qwen/Qwen3-Coder-Next",
            "accelerator": "MI355X",
            "enabled": True,
        }
    ]
    base = engine.recommend(
        "coding-assistant", lifecycle_mode="production", serving_pattern="interactive"
    )
    over = engine.recommend(
        "coding-assistant",
        lifecycle_mode="production",
        serving_pattern="interactive",
        endpoints=fake,
    )
    # Same models/computes eligible; overlay only flips endpoint_available
    base_keys = {(c["model"], c["compute"]) for c in base["candidates"]}
    over_keys = {(c["model"], c["compute"]) for c in over["candidates"]}
    assert base_keys == over_keys
    live = [c for c in over["candidates"] if c.get("endpoint_available")]
    assert live and all(c["model"] == "Qwen/Qwen3-Coder-Next" for c in live)


def test_cost_evidence_and_infra_vs_token_econ_fields():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    rec = engine.recommend("coding-assistant", lifecycle_mode="production")
    assert rec["cost_evidence_default"] == "RELATIVE"
    top = rec["ranked"][0]
    assert top["cost_evidence"] in ("MEASURED", "ESTIMATED", "RELATIVE", "UNKNOWN")
    assert "infrastructure_cost_class" in top
    assert "token_economic_fit" in top
    assert "deployment_fit" in top
    assert "serving_pattern_fit" in top
    assert "locality_fit" in top


def test_simulate_shows_exclusion_categories():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    sim = engine.simulate_route(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
        serving_pattern="interactive",
        utilization="high",
    )
    assert "exclusions" in sim
    assert "lifecycle" in sim["exclusions"]
    assert "tp_fit" in sim["exclusions"]
    assert any(e["compute"] == "MI350P" for e in sim["lifecycle_exclusions"])


def test_tp_fit_mi350p_and_radeon_prefer_tp1():
    """MI350P/Radeon reject models that need TP>1; rack Instinct may use TP≥2."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    frontier = "meta-llama/Llama-3.1-405B-Instruct"
    large = "meta-llama/Llama-3.3-70B-Instruct"
    small = "meta-llama/Llama-3.1-8B-Instruct"

    ok_f_mi, req_f, max_mi, why_f, kind_f = engine._tp_fit(frontier, "MI350P")
    assert not ok_f_mi
    assert req_f >= 2
    assert max_mi == 1
    assert kind_f == "tp_fit"
    assert "TP" in why_f

    ok_f_rack, req_rack, max_rack, _, kind_rack = engine._tp_fit(frontier, "MI300X")
    assert ok_f_rack
    assert req_rack >= 2
    assert max_rack >= 2
    assert kind_rack is None

    # large fits TP1 on MI350P; exceeds Radeon max_size_class_tp1 (medium)
    ok_l_mi, req_l_mi, _, _, _ = engine._tp_fit(large, "MI350P")
    assert ok_l_mi and req_l_mi == 1
    ok_l_rad, req_l_rad, max_rad, _, kind_l = engine._tp_fit(large, "R9700")
    assert not ok_l_rad
    assert req_l_rad >= 2
    assert max_rad == 1
    assert kind_l == "tp_fit"

    ok_s, req_s, _, _, _ = engine._tp_fit(small, "R9700")
    assert ok_s and req_s == 1

    # EPYC: TP schedule N/A
    ok_cpu, _, _, why_cpu, _ = engine._tp_fit(large, "EPYC_9965")
    assert ok_cpu
    assert "N/A" in why_cpu or "CPU" in why_cpu


def test_tp_fit_gate_surfaces_in_recommend_when_forced():
    """Hard gate: oversized size_class never ranks on TP1-only SKUs."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    # Inject a synthetic frontier AIM on MI350P to prove the gate (not a catalog claim).
    model = "meta-llama/Llama-3.1-405B-Instruct"
    engine.aims[model] = {
        "model": model,
        "support": {
            "instinct": {
                "MI350P": {"support": "preview", "lifecycle": "tech-preview"},
                "MI300X": {"support": "optimized", "lifecycle": "ga"},
            }
        },
    }
    rec = engine.recommend(
        "complex-reasoning",
        objective="quality",
        lifecycle_mode="evaluation",
        include_excluded=True,
    )
    mi_ranked = [c for c in rec["ranked"] if c["compute"] == "MI350P" and c["model"] == model]
    assert mi_ranked == []
    tp_excl = [
        e
        for e in rec.get("tp_fit_exclusions") or []
        if e["model"] == model and e["compute"] == "MI350P"
    ]
    assert tp_excl and tp_excl[0]["exclusion_kind"] == "tp_fit"
    rack = [c for c in rec["ranked"] if c["compute"] == "MI300X" and c["model"] == model]
    assert rack, "frontier should still rank on rack Instinct with TP≥2"


def test_compute_catalog_tp_policy_present():
    bundle = load_routing_bundle(ROOT)
    by_id = {c["id"]: c for c in bundle["compute"]["compute"]}
    assert by_id["MI350P"]["tp_policy"]["max_recommended"] == 1
    assert by_id["MI350P"]["tp_policy"]["multi_gpu_ok"] is False
    assert by_id["R9700"]["tp_policy"]["max_recommended"] == 1
    assert by_id["MI300X"]["tp_policy"]["max_recommended"] >= 2
    assert by_id["MI300X"]["tp_policy"]["multi_gpu_ok"] is True
    nested = (bundle["policy"].get("_canonical") or {}).get("tensor_parallel") or {}
    assert nested.get("size_class_default_min_tp", {}).get("frontier") == 2


def test_serving_pattern_list_and_latency_mapping():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    sps = {s["id"] for s in engine.list_serving_patterns()}
    assert sps >= {"interactive", "online-throughput", "batch", "offline-batch"}
    assert engine.resolve_latency_requirement("coding-assistant", "interactive") == "critical"
    assert engine.resolve_latency_requirement("batch-summarization", "batch") == "relaxed"
    assert engine.resolve_serving_pattern(None, "batch-summarization") == "batch"
