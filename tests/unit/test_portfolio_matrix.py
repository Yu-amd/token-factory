"""Portfolio Matrix tests — full catalog rows, no silent truncation (§§48–57)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from token_factory.routing_matrix import (
    RecommendationEngine,
    audit_catalog,
    audit_matrix,
    load_routing_bundle,
    normalize_model_id,
)
from token_factory.routing_matrix.portfolio import catalog_model_ids

ROOT = Path(__file__).resolve().parents[2]


def test_portfolio_rows_equal_full_catalog():
    """§48 — rows == full merged AIM catalog."""
    bundle = load_routing_bundle(ROOT)
    engine = RecommendationEngine(bundle)
    catalog = catalog_model_ids(bundle)
    matrix = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    assert sorted(matrix["rows"]) == sorted(catalog)
    assert len(matrix["rows"]) == len(catalog)
    assert matrix["view_mode"] == "portfolio"
    assert matrix["catalog_counts"]["catalog_models"] == len(catalog)


def test_portfolio_every_model_has_every_compute_cell():
    """§49 — every model × compute column has a cell."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    cols = matrix["columns_all"]
    assert "MI250X" in cols
    assert "EPYC_ZEN4" in cols
    assert "EPYC_ZEN5" in cols
    for model in matrix["rows"]:
        assert set(matrix["cells"][model].keys()) == set(cols)
        for compute, cell in matrix["cells"][model].items():
            assert cell["model"] == model
            assert cell["compute"] == compute
            assert "matrix_mark" in cell


def test_portfolio_no_silent_truncation():
    """§50 — Portfolio display_rows equals catalog when Show=all (no top-14 silence)."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    assert len(matrix["display_rows"]) == len(matrix["rows"])
    assert matrix.get("coverage_warning") is None


def test_executive_may_truncate_with_label():
    """§51 — Executive View may truncate; coverage warning + view_label set."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix("coding-assistant", view_mode="executive", show="all")
    assert matrix["view_mode"] == "executive"
    assert "Executive" in (matrix.get("view_label") or "")
    assert len(matrix["rows"]) == len(catalog_model_ids(engine.bundle))
    assert len(matrix["display_rows"]) <= len(matrix["rows"])
    if len(matrix["display_rows"]) < len(matrix["rows"]):
        assert matrix.get("coverage_warning")
        assert str(len(matrix["display_rows"])) in matrix["coverage_warning"]


def test_metadata_incomplete_visible_in_portfolio():
    """§52 — metadata-incomplete models stay visible with row_status."""
    bundle = load_routing_bundle(ROOT)
    # Strip capabilities from one AIM model
    target = catalog_model_ids(bundle)[0]
    models = []
    for m in bundle["models"]["models"]:
        entry = deepcopy(m)
        if entry["model"] == target:
            entry["capabilities"] = {}
        models.append(entry)
    bundle["models"]["models"] = models
    engine = RecommendationEngine(bundle)
    matrix = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    assert target in matrix["display_rows"]
    assert matrix["row_status"][target] == "metadata_incomplete"
    assert matrix["why_not_recommended"][target]


def test_lifecycle_excluded_visible_in_portfolio():
    """§53 — lifecycle-excluded AIMs remain visible under Production."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "simple-chat",
        view_mode="portfolio",
        show="all",
        lifecycle_mode="production",
        deployment="enterprise",
    )
    # Radeon preview / MI350P TP models must appear in rows+display
    radeon_model = "meta-llama/Llama-3.1-8B-Instruct"
    assert radeon_model in matrix["rows"]
    assert radeon_model in matrix["display_rows"]
    cell = matrix["cells"][radeon_model].get("R9700")
    assert cell is not None
    assert cell.get("aim_support") == "preview"
    assert cell.get("lifecycle_excluded") or cell.get("lifecycle") == "preview"
    assert cell.get("matrix_mark") != "—"


def test_capability_mismatch_not_dash():
    """§54 — capability mismatch uses ◌/○ + row_status, not '—'."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "vlm",
        view_mode="portfolio",
        show="all",
        lifecycle_mode="production-preview",
    )
    text_only = "Qwen/Qwen3.5-9B"
    assert text_only in matrix["display_rows"]
    assert matrix["row_status"][text_only] == "capability_excluded"
    # AIM support cells must not be —
    support_marks = [
        c["matrix_mark"]
        for c in matrix["cells"][text_only].values()
        if c.get("aim_support") is not None
    ]
    assert support_marks
    assert all(m != "—" for m in support_marks)
    assert any(m == "◌" for m in support_marks)
    # True unsupported compute stays —
    mi = matrix["cells"][text_only].get("MI355X")
    if mi and mi.get("aim_support") is None:
        assert mi["matrix_mark"] == "—"


def test_alias_normalization_in_catalog_universe():
    """§55 — aliases collapse supplied TP spellings into one catalog row."""
    bundle = load_routing_bundle(ROOT)
    aliases = bundle["aliases"]
    supplied = "mistralai/Mistral-Small-3.2-24B-Instruct-2501"
    canonical = normalize_model_id(supplied, aliases)
    assert canonical != supplied or supplied in catalog_model_ids(bundle)
    assert canonical in catalog_model_ids(bundle)
    engine = RecommendationEngine(bundle)
    matrix = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    assert canonical in matrix["rows"]
    assert supplied not in matrix["rows"] or supplied == canonical


def test_portfolio_filters_search_vendor_show():
    """§56 — display_rows shrink only via explicit Show/search/vendor filters."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    full = engine.matrix("coding-assistant", view_mode="portfolio", show="all")
    qwen = engine.matrix(
        "coding-assistant", view_mode="portfolio", show="all", search="Qwen"
    )
    assert 0 < len(qwen["display_rows"]) < len(full["display_rows"])
    assert all("Qwen" in m or "qwen" in m.lower() for m in qwen["display_rows"])
    assert len(qwen["rows"]) == len(full["rows"])  # rows stay full catalog

    vendor = engine.matrix(
        "coding-assistant", view_mode="portfolio", show="all", vendor="meta-llama"
    )
    assert vendor["display_rows"]
    assert all(m.startswith("meta-llama/") for m in vendor["display_rows"])

    rec = engine.matrix(
        "coding-assistant", view_mode="portfolio", show="recommended"
    )
    assert rec["display_rows"]
    assert all(rec["row_status"][m] == "recommended" for m in rec["display_rows"])


def test_compute_group_filters_columns_not_rows():
    """§57 — Instinct|EPYC|Radeon group toggles columns; Portfolio rows stay full."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    all_m = engine.matrix(
        "coding-assistant", view_mode="portfolio", show="all", compute_group="all"
    )
    instinct = engine.matrix(
        "coding-assistant", view_mode="portfolio", show="all", compute_group="instinct"
    )
    assert len(instinct["rows"]) == len(all_m["rows"])
    assert len(instinct["display_rows"]) == len(all_m["display_rows"])
    assert all(
        (engine.compute[c]["family"] == "instinct") for c in instinct["columns"]
    )
    assert "MI250X" in instinct["columns"]
    assert "R9700" not in instinct["columns"]


def test_catalog_and_matrix_audit_counts():
    cat = audit_catalog(ROOT)
    assert cat["merged_catalog_models"] == len(cat["merged_models"])
    assert cat["ga_aims"] >= 1
    assert cat["compute_columns"] >= 8
    assert cat["amd_docs_reconcile"]["runtime_scrape"] is False
    mx = audit_matrix("coding-assistant", view_mode="portfolio", root=ROOT, show="all")
    assert mx["rows"] == cat["merged_catalog_models"]
    assert mx["display_rows"] == cat["merged_catalog_models"]
    assert mx["catalog_counts"]["catalog_models"] == cat["merged_catalog_models"]


def test_ranking_still_selective_while_portfolio_shows_unsuitable():
    """Ranking eligible-only; unsuitable stay visible in Portfolio."""
    engine = RecommendationEngine(load_routing_bundle(ROOT))
    matrix = engine.matrix(
        "vlm", view_mode="portfolio", show="all", lifecycle_mode="production-preview"
    )
    ranked_models = {c["model"] for c in matrix["ranked"]}
    assert "Qwen/Qwen3.5-9B" not in ranked_models
    assert "Qwen/Qwen3.5-9B" in matrix["display_rows"]
    assert matrix["row_status"]["Qwen/Qwen3.5-9B"] == "capability_excluded"
