"""AIM catalog and eligibility tests."""

from pathlib import Path

from token_factory.catalog import (
    endpoint_eligibility,
    find_aim,
    load_catalog,
    select_fallback_endpoint,
)
from token_factory.config import load_endpoints

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_has_gpt_oss_models():
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    aim = find_aim(catalog, "openai/gpt-oss-120b")
    assert aim is not None
    assert aim["support"]["instinct"]["MI350X"] == "optimized"


def test_endpoint_eligibility_optimized():
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    ep = next(e for e in endpoints["endpoints"] if e["id"] == "gpt-oss-120b-coding")
    result = endpoint_eligibility(ep, catalog, min_support="optimized")
    assert result["eligible"] is True
    assert result["support_level"] == "optimized"


def test_fallback_selection():
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")["endpoints"]
    selected = select_fallback_endpoint(
        endpoints,
        catalog,
        chain=["gpt-oss-20b-general", "gpt-oss-120b-coding"],
    )
    assert selected is not None
    assert selected["id"] in {"gpt-oss-20b-general", "gpt-oss-120b-coding"}
