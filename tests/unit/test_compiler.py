"""Compiler tests."""

from pathlib import Path

import yaml

from token_factory.catalog import load_catalog
from token_factory.compiler import compile_all
from token_factory.config import load_endpoints, load_policies, load_token_factory

ROOT = Path(__file__).resolve().parents[2]


def test_compile_outputs(tmp_path):
    endpoints = load_endpoints(ROOT / "config" / "endpoints.example.yaml")
    policies = load_policies(ROOT / "config" / "policies.example.yaml")
    token_factory = load_token_factory(ROOT / "config" / "token-factory.example.yaml")
    catalog = load_catalog(ROOT / "catalog" / "aims.yaml")
    outputs = compile_all(endpoints, policies, token_factory, catalog, output_dir=tmp_path)

    sr = yaml.safe_load(outputs["semantic_router_values"].read_text())
    assert sr["dashboard"]["enabled"] is True
    assert sr["dashboard"]["service"]["port"] == 8700
    assert sr["config"]["version"] == "v0.3"
    assert len(sr["config"]["routing"]["decisions"]) >= 3
    assert sr["config"]["global"]["router"]["auto_model_name"] == "token-factory/auto"

    manifests = list(yaml.safe_load_all(outputs["ai_gateway_manifests"].read_text()))
    kinds = {m["kind"] for m in manifests}
    assert "AIGatewayRoute" in kinds
    assert "AIServiceBackend" in kinds
    assert "ClientTrafficPolicy" in kinds
    assert "ReferenceGrant" in kinds
    assert "BackendTrafficPolicy" in kinds
    btp = [m for m in manifests if m["kind"] == "BackendTrafficPolicy"]
    assert btp[0]["spec"]["healthCheck"]["active"]["http"]["path"] == "/v1/models"
    extproc = next(m for m in manifests if m["kind"] == "EnvoyPatchPolicy")
    assert len(extproc["spec"]["jsonPatches"]) == 2
    cluster_patch = extproc["spec"]["jsonPatches"][1]
    assert cluster_patch["operation"]["value"]["type"] == "STRICT_DNS"

    ui = __import__("json").loads(outputs["ui_metadata"].read_text())
    assert ui["virtual_model"] == "token-factory/auto"
