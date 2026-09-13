"""Routing Matrix PowerPoint-ready export tests."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from token_factory.routing_matrix import (
    RecommendationEngine,
    export_all_use_cases,
    export_routing_matrix,
    get_current_matrix_projection,
    load_routing_bundle,
    resolve_export,
)
from token_factory.routing_matrix.executive import (
    ANTI_BENCHMARK,
    build_executive_slide,
    render_executive_png,
)
from token_factory.routing_matrix.export import (
    CSV_FIELDS,
    export_filename,
    normalize_style,
    projection_to_csv_rows,
)
from token_factory.routing_matrix.projection import display_columns, display_rows

ROOT = Path(__file__).resolve().parents[2]
FIXED_TS = datetime(2026, 9, 13, 20, 0, 0, tzinfo=timezone.utc)


def _engine() -> RecommendationEngine:
    return RecommendationEngine(load_routing_bundle(ROOT))


def _matrix(**kwargs):
    defaults = {
        "use_case_id": "coding-assistant",
        "objective": "balanced",
        "lifecycle_mode": "production",
        "view_mode": "portfolio",
        "show": "all",
        "compute_group": "all",
    }
    defaults.update(kwargs)
    uc = defaults.pop("use_case_id")
    return _engine().matrix(uc, **defaults)


def test_current_view_projection_matches_display_helpers():
    matrix = _matrix(view_mode="executive", show="suitable")
    proj = get_current_matrix_projection(matrix)
    assert proj.rows == display_rows(matrix)
    assert proj.columns == display_columns(matrix)
    assert proj.rows == list(matrix["display_rows"] or matrix["rows"])
    for model in proj.rows:
        assert set(proj.cells[model].keys()) == set(proj.columns)


def test_current_view_csv_exactness_full_matrix():
    matrix = _matrix(view_mode="portfolio", show="recommended", search="Qwen")
    proj = get_current_matrix_projection(matrix)
    result = export_routing_matrix(matrix, format="csv", style="full", timestamp=FIXED_TS)
    assert result.filename.startswith("token-factory-routing-")
    assert result.filename.endswith(".csv")
    text = result.data.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    fields = reader.fieldnames or []
    assert "use_case" not in fields  # full current-view default omits unless zip/all
    assert "model" in fields and "compute" in fields
    assert "recommendation" in fields and "confidence" in fields
    rows = list(reader)
    expected = projection_to_csv_rows(proj, include_use_case=False)
    assert len(rows) == len(expected)
    assert len(rows) == len(proj.rows) * len(proj.columns)
    for got, exp in zip(rows, expected, strict=True):
        assert got["model"] == exp["model"]
        assert got["compute"] == exp["compute"]
        assert got["recommendation"] == str(exp["recommendation"] or "")
        assert got["confidence"] == str(exp["confidence"] or "")
        assert got["matrix_mark"] == str(exp["matrix_mark"] or "")
        assert got["row_status"] == str(exp["row_status"] or "")


def test_export_does_not_change_status_or_confidence():
    matrix = _matrix()
    before = {}
    for model, cols in (matrix.get("cells") or {}).items():
        for compute, cell in (cols or {}).items():
            before[(model, compute)] = (
                cell.get("recommendation"),
                cell.get("confidence"),
                cell.get("evidence_badge"),
                cell.get("matrix_mark"),
                (matrix.get("row_status") or {}).get(model),
            )
    export_routing_matrix(matrix, format="png", style="executive", timestamp=FIXED_TS)
    export_routing_matrix(matrix, format="csv", style="full", timestamp=FIXED_TS)
    for model, cols in (matrix.get("cells") or {}).items():
        for compute, cell in (cols or {}).items():
            assert before[(model, compute)] == (
                cell.get("recommendation"),
                cell.get("confidence"),
                cell.get("evidence_badge"),
                cell.get("matrix_mark"),
                (matrix.get("row_status") or {}).get(model),
            )


def test_filename_sanitized_and_prefixed():
    name = export_filename(
        use_case="Coding Assistant!",
        lifecycle="production",
        view="executive",
        style="executive",
        fmt="png",
        timestamp=FIXED_TS,
    )
    assert name == (
        "token-factory-routing-coding-assistant-production-executive-executive-20260913T200000Z.png"
    )
    assert "!" not in name
    assert " " not in name
    assert normalize_style("slide") == "executive"


def test_png_signature_dimensions_and_metadata_strings():
    matrix = _matrix(view_mode="executive")
    result = export_routing_matrix(matrix, format="png", style="executive", timestamp=FIXED_TS)
    assert result.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(result.data) > 1000
    img = Image.open(io.BytesIO(result.data))
    assert img.size == (1920, 1080)
    proj = get_current_matrix_projection(matrix)
    assert proj.policy_version
    assert ANTI_BENCHMARK
    full = export_routing_matrix(matrix, format="png", style="full", timestamp=FIXED_TS)
    full_img = Image.open(io.BytesIO(full.data))
    assert full_img.size[0] >= 1280
    assert full_img.size[1] >= 720


def test_export_metadata_includes_policy_and_legend_statuses():
    matrix = _matrix()
    proj = get_current_matrix_projection(matrix)
    assert proj.policy_version is not None
    assert proj.lifecycle_mode == "production"
    assert proj.view_mode == "portfolio"
    from token_factory.routing_matrix.projection import status_legend_names

    names = status_legend_names()
    assert "recommended" in names
    assert "lifecycle_excluded" in names
    assert "capability_excluded" in names


def test_all_use_cases_executive_zip_one_png_each():
    engine = _engine()
    expected_ids = [u["id"] for u in engine.list_use_cases()]
    result = export_all_use_cases(
        engine,
        matrix_kwargs={
            "objective": "balanced",
            "lifecycle_mode": "production",
            "view_mode": "executive",
            "show": "all",
        },
        format="zip",
        style="executive",
        timestamp=FIXED_TS,
    )
    assert result.scope == "all"
    assert result.filename.startswith("token-factory-routing-all-use-cases-")
    assert result.mime == "application/zip"
    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        names = set(zf.namelist())
        assert "README.txt" in names
        assert "index.csv" in names
        assert "all-use-cases.csv" in names
        readme = zf.read("README.txt").decode("utf-8")
        assert ANTI_BENCHMARK in readme
        assert f"Policy version: {get_current_matrix_projection(_matrix()).policy_version}" in readme
        index = list(csv.DictReader(io.StringIO(zf.read("index.csv").decode("utf-8"))))
        assert [r["use_case"] for r in index] == expected_ids
        for i, uc in enumerate(expected_ids, start=1):
            assert f"{i:02d}-{uc}-executive.png" in names
            assert f"{i:02d}-{uc}-executive.csv" in names
            png = zf.read(f"{i:02d}-{uc}-executive.png")
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
            assert Image.open(io.BytesIO(png)).size == (1920, 1080)
        combined = list(csv.DictReader(io.StringIO(zf.read("all-use-cases.csv").decode("utf-8"))))
        assert combined
        assert "use_case" in (combined[0].keys())
        assert {r["use_case"] for r in combined} == set(expected_ids)


def test_all_png_coerces_to_zip():
    engine = _engine()
    result = resolve_export(
        engine=engine,
        scope="all",
        format="png",
        style="executive",
        matrix_kwargs={"lifecycle_mode": "production", "view_mode": "portfolio", "show": "recommended"},
        timestamp=FIXED_TS,
    )
    assert result.format == "zip"
    assert result.note
    assert "ZIP" in result.note
    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        assert any(n.endswith("-executive.png") for n in zf.namelist())


def test_current_zip_bundle_contents_full():
    matrix = _matrix(use_case_id="simple-chat")
    result = export_routing_matrix(matrix, format="zip", style="full", timestamp=FIXED_TS)
    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        names = set(zf.namelist())
        assert "README.txt" in names
        assert "index.csv" in names
        assert "all-use-cases.csv" in names
        assert "simple-chat/matrix.png" in names
        assert "simple-chat/matrix.csv" in names
        png = zf.read("simple-chat/matrix.png")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_csv_fields_are_real_only():
    for field in CSV_FIELDS:
        assert field  # non-empty
    assert "winner" not in CSV_FIELDS
    assert "benchmark" not in CSV_FIELDS


def test_executive_export_top_n():
    matrix = _matrix()
    proj = get_current_matrix_projection(matrix)
    for n in (3, 5, 10):
        slide = build_executive_slide(proj, top_n=n, timestamp=FIXED_TS)
        assert len(slide.alternatives) <= n
        assert slide.top_n == n
        ranked = list(matrix.get("ranked") or [])
        assert len(slide.alternatives) == min(n, len(ranked))
    csv_result = export_routing_matrix(
        matrix, format="csv", style="executive", top_n=3, timestamp=FIXED_TS
    )
    rows = list(csv.DictReader(io.StringIO(csv_result.data.decode("utf-8"))))
    assert len(rows) == 3
    assert rows[0]["rank"] == "1"


def test_executive_csv_omits_confidence():
    matrix = _matrix()
    result = export_routing_matrix(
        matrix, format="csv", style="executive", top_n=5, timestamp=FIXED_TS
    )
    reader = csv.DictReader(io.StringIO(result.data.decode("utf-8")))
    fields = reader.fieldnames or []
    assert "confidence" not in fields
    assert "runtime" not in fields
    assert "rank" in fields and "recommendation" in fields and "lifecycle" in fields
    rows = list(reader)
    assert rows
    assert "confidence" not in rows[0]


def test_executive_preferred_matches_canonical_ranking():
    matrix = _matrix()
    ranked = matrix["ranked"]
    assert ranked
    proj = get_current_matrix_projection(matrix)
    slide = build_executive_slide(proj, top_n=5, timestamp=FIXED_TS)
    assert slide.preferred is not None
    assert slide.preferred.model == ranked[0]["model"]
    assert slide.preferred.compute == ranked[0]["compute"]
    assert slide.preferred.confidence == str(ranked[0].get("confidence") or "—")
    assert slide.preferred.recommendation == "Preferred" or ranked[0]["recommendation"]
    for i, row in enumerate(slide.alternatives):
        assert row.model == ranked[i]["model"]
        assert row.compute == ranked[i]["compute"]


def test_runtime_does_not_rewrite_preferred():
    """Inventory must not change canonical preferred; Executive Slide stays policy-first."""
    engine = _engine()
    base = engine.matrix(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
        show="all",
    )
    preferred = base["ranked"][0]
    alt = next(
        c
        for c in base["ranked"][1:]
        if (c["model"], c["compute"]) != (preferred["model"], preferred["compute"])
    )
    endpoints = [
        {
            "id": "alt-live",
            "model": alt["model"],
            "accelerator": alt["compute"],
            "enabled": True,
        }
    ]
    matrix = engine.matrix(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
        show="all",
        endpoints=endpoints,
    )
    assert matrix["inventory_provided"] is True
    ranked = matrix["ranked"]
    assert ranked[0]["model"] == preferred["model"]
    assert ranked[0]["compute"] == preferred["compute"]
    assert ranked[0].get("endpoint_available") is False
    proj = get_current_matrix_projection(matrix)
    slide = build_executive_slide(proj, top_n=5, timestamp=FIXED_TS)
    assert slide.preferred is not None
    assert slide.preferred.model == preferred["model"]
    assert slide.preferred.compute == preferred["compute"]
    # Executive Slide is policy-first: no runtime escalation callout / rewrite
    assert slide.escalation is None
    assert "policy" in slide.runtime_banner.lower()
    assert "fallback" not in slide.runtime_banner.lower()
    assert "Canonical policy recommendation" in slide.runtime_banner
    png = render_executive_png(slide)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    with Image.open(io.BytesIO(png)) as img:
        assert img.size == (1920, 1080)


def test_executive_confidence_evidence_policy_footer():
    matrix = _matrix()
    proj = get_current_matrix_projection(matrix)
    slide = build_executive_slide(proj, top_n=5, timestamp=FIXED_TS)
    assert slide.policy_version == proj.policy_version
    assert ANTI_BENCHMARK in slide.footer
    assert f"Policy v{proj.policy_version}" in slide.footer
    assert "2026-09-13" in slide.footer
    assert slide.preferred is not None
    pe = slide.preferred.performance_evidence_status
    if pe != "AMD_MEASURED":
        assert any("Not yet available" in line or pe in line for line in slide.evidence_lines)
    assert "Canonical policy" in slide.runtime_banner or "policy" in slide.runtime_banner.lower()
    assert "Unavailable" not in slide.runtime_banner


def test_executive_available_when_preferred_deployed():
    """Deployed inventory must not change Executive Slide away from policy framing."""
    engine = _engine()
    base = engine.matrix("coding-assistant", objective="balanced", lifecycle_mode="production")
    pref = base["ranked"][0]
    endpoints = [
        {
            "id": "pref-live",
            "model": pref["model"],
            "accelerator": pref["compute"],
            "enabled": True,
        }
    ]
    matrix = engine.matrix(
        "coding-assistant",
        objective="balanced",
        lifecycle_mode="production",
        endpoints=endpoints,
    )
    slide = build_executive_slide(
        get_current_matrix_projection(matrix), top_n=5, timestamp=FIXED_TS
    )
    assert slide.preferred is not None
    assert slide.preferred.model == pref["model"]
    assert slide.escalation is None
    assert "policy" in slide.runtime_banner.lower()
