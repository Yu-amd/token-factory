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
    from token_factory.config import load_policies, load_endpoints, load_token_factory, validate_all
    from token_factory.catalog import load_catalog

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
        if cell:
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
            if cols.get("MI350P")
        ]
        r9_cells = [
            (m, cols["R9700"])
            for m, cols in matrix["cells"].items()
            if cols.get("R9700")
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
        if cols.get("MI350P")
    ]
    r9_cells = [
        cols["R9700"]
        for cols in matrix["cells"].values()
        if cols.get("R9700")
    ]
    assert mi_cells, "MI350P column must not be empty under Production"
    assert r9_cells, "R9700 column must not be empty under Production"
    assert all(c.get("lifecycle_excluded") for c in mi_cells)
    assert all(c.get("lifecycle_excluded") for c in r9_cells)
    assert all(c.get("availability") == "private-eval" for c in mi_cells + r9_cells)
    assert any(m in matrix["display_rows"] for m, cols in matrix["cells"].items() if cols.get("MI350P"))
    assert any(m in matrix["display_rows"] for m, cols in matrix["cells"].items() if cols.get("R9700"))
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


def test_coding_specialization_beats_size_soft_bias_same_compute():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    # Performance card must prefer coding-specialized AIM
    cards = engine.summary_cards(
        "coding-assistant", lifecycle_mode="production", serving_pattern="interactive"
    )
    perf = cards["cards"]["best_performance"]["candidate"]
    assert engine.models[perf["model"]].get("specialization") == "coding" or "Coder" in perf["model"]
    # On the same compute as a non-specialized peer, coding-specialized ranks better
    rec = engine.recommend(
        "coding-assistant",
        objective="quality",
        lifecycle_mode="production",
        serving_pattern="interactive",
    )
    by_compute: dict[str, list] = {}
    for c in rec["ranked"]:
        by_compute.setdefault(c["compute"], []).append(c)
    for compute, rows in by_compute.items():
        coder = next((c for c in rows if engine.models[c["model"]].get("specialization") == "coding"), None)
        general = next(
            (
                c
                for c in rows
                if engine.models[c["model"]].get("specialization") != "coding"
                and engine.models[c["model"]].get("size_class") in ("large", "frontier", "medium")
            ),
            None,
        )
        if coder and general:
            assert coder["rank"] < general["rank"], (compute, coder["model"], general["model"])
            break
    else:
        # At least overall #1 is coding-specialized
        assert engine.models[rec["ranked"][0]["model"]].get("specialization") == "coding"


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
    assert any(e["compute"] == "MI350P" for e in sim["lifecycle_exclusions"])


def test_serving_pattern_list_and_latency_mapping():
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    sps = {s["id"] for s in engine.list_serving_patterns()}
    assert sps >= {"interactive", "online-throughput", "batch", "offline-batch"}
    assert engine.resolve_latency_requirement("coding-assistant", "interactive") == "critical"
    assert engine.resolve_latency_requirement("batch-summarization", "batch") == "relaxed"
    assert engine.resolve_serving_pattern(None, "batch-summarization") == "batch"
