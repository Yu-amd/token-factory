"""Config parse and validation tests."""

from pathlib import Path

from token_factory.catalog import load_catalog
from token_factory.config import load_endpoints, load_policies, load_token_factory, validate_all
from token_factory.config.validator import validate_cross_references

ROOT = Path(__file__).resolve().parents[2]


def test_load_example_configs():
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    policies = load_policies(ROOT / "config" / "policies.example.yaml")
    token_factory = load_token_factory(ROOT / "config" / "token-factory.example.yaml")
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    validate_all(endpoints, policies, token_factory, catalog)


def test_invalid_endpoint_reference():
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    policies = load_policies(ROOT / "config" / "policies.example.yaml")
    policies["policy"]["routes"][0]["endpoint_ref"] = "missing-endpoint"
    errors = validate_cross_references(endpoints, policies)
    assert any("missing-endpoint" in e for e in errors)


def test_policy_profiles_validate():
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    token_factory = load_token_factory(ROOT / "config" / "token-factory.example.yaml")
    for profile in (ROOT / "policies").glob("amd-*.yaml"):
        policies = __import__("yaml").safe_load(profile.read_text())
        validate_all(endpoints, policies, token_factory, catalog)
