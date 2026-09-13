"""Tests for Automated Demo scenario loading, validation, runner, CI exit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from token_factory.demo.injection import apply_endpoint_overlay, normalize_injections
from token_factory.demo.loader import expand_requests, list_packs, load_pack, scenarios_dir
from token_factory.demo.models import ValidationStatus
from token_factory.demo.normalize import classification_matches, normalize_label
from token_factory.demo.observability import DemoInstrumentor
from token_factory.demo.runner import DemoRunner
from token_factory.demo.schema import ScenarioSchemaError, assert_valid_pack, validate_pack
from token_factory.demo.validation import validate_request

ROOT = Path(__file__).resolve().parents[2]


def test_scenarios_dir_exists():
    assert scenarios_dir().is_dir()


def test_all_packs_load():
    packs = list_packs()
    ids = {p["id"] for p in packs if not p.get("error")}
    assert {"smoke", "executive", "enterprise-mixed", "observability", "fallback"} <= ids
    for pid in ids:
        doc = load_pack(pid)
        assert doc["id"] == pid
        assert doc.get("scenarios")


def test_smoke_pack_request_count():
    pack = load_pack("smoke")
    specs = expand_requests(pack)
    assert 8 <= len(specs) <= 12


def test_invalid_schema_fails():
    with pytest.raises(ScenarioSchemaError):
        assert_valid_pack({"id": "bad", "display_name": "Bad"})  # missing scenarios


def test_validate_pack_reports_errors():
    errors = validate_pack({"id": "x", "display_name": "x", "scenarios": []})
    assert errors


def test_classification_normalize_aliases():
    assert classification_matches("coding-assistant", "computer science")
    assert classification_matches("coding-assistant", "coding_route")
    assert classification_matches("complex-reasoning", "math")
    assert classification_matches("enterprise-chat", "business")
    assert not classification_matches("coding-assistant", "chemistry")
    assert normalize_label("Computer Science") == "computer science"


def test_capability_vision_failure():
    result = validate_request(
        expected={"capabilities": {"required": ["vision"]}},
        actual={
            "model_capabilities": {"vision": False},
            "text_only_for_vision": True,
            "runtime_selected": {"model": "text-only", "compute": "MI300X"},
        },
    )
    assert result["capability"] == ValidationStatus.FAIL.value


def test_lifecycle_tp_under_production_fails():
    result = validate_request(
        expected={"routing": {"require_production_eligible": True}, "lifecycle_exclusion": True},
        actual={
            "lifecycle_mode": "production",
            "runtime_selected": {
                "model": "x",
                "compute": "MI350P",
                "lifecycle": "tech-preview",
                "production_eligible": False,
            },
            "lifecycle_exclusions_count": 0,
            "tp_excluded": False,
        },
    )
    assert result["lifecycle"] == ValidationStatus.FAIL.value


def test_lifecycle_tp_excluded_passes():
    result = validate_request(
        expected={"lifecycle_exclusion": True, "routing": {"require_production_eligible": True}},
        actual={
            "lifecycle_mode": "production",
            "runtime_selected": {
                "model": "openai/gpt-oss-120b",
                "compute": "MI300X",
                "lifecycle": "ga",
                "production_eligible": True,
            },
            "lifecycle_exclusions_count": 3,
            "tp_excluded": True,
        },
    )
    assert result["lifecycle"] == ValidationStatus.PASS.value


def test_locality_warn_without_radeon():
    result = validate_request(
        expected={"routing": {"require_local": True, "allow_no_runtime": True}},
        actual={
            "runtime_selected": {"model": "x", "compute": "MI300X", "family": "instinct"},
            "selected_compute_family": "instinct",
            "no_local_candidate": True,
        },
    )
    assert result["policy"] == ValidationStatus.WARN.value


def test_canonical_vs_runtime_preferred_not_deployed():
    result = validate_request(
        expected={"routing": {"preferred_compute_family": ["instinct"]}},
        actual={
            "canonical_preferred": {"model": "A", "compute": "MI355X"},
            "runtime_selected": {
                "model": "openai/gpt-oss-120b",
                "compute": "MI300X",
                "family": "instinct",
                "endpoint_available": True,
                "endpoint_id": "gpt-oss-120b-coding",
                "lifecycle": "ga",
                "production_eligible": True,
            },
            "preferred_not_deployed": True,
            "canonical_vs_runtime_reason": "preferred candidate not deployed",
            "selected_endpoint": "gpt-oss-120b-coding",
            "policy_version": "2.4",
        },
    )
    assert result["route"] == ValidationStatus.PASS.value
    assert result["endpoint"] == ValidationStatus.PASS.value


def test_injection_overlay_does_not_mutate_source():
    endpoints = [
        {"id": "a", "hardware": "instinct", "accelerator": "MI300X", "enabled": True},
        {"id": "b", "hardware": "radeon", "accelerator": "R9700", "enabled": True, "tags": ["local"]},
        {"id": "c", "hardware": "epyc", "accelerator": "EPYC_9965", "enabled": True},
    ]
    original = json.loads(json.dumps(endpoints))
    out = apply_endpoint_overlay(endpoints, ["no-radeon", "no-epyc"])
    assert endpoints == original
    ids = {e["id"] for e in out}
    assert ids == {"a"}


def test_normalize_injections():
    assert normalize_injections(["preferred_endpoint_unavailable", "no-radeon"]) == [
        "preferred-endpoint-unavailable",
        "no-radeon",
    ]


def test_seed_reproducibility_enterprise_mixed():
    pack = load_pack("enterprise-mixed")
    a = expand_requests(pack, seed=42, requests=20)
    b = expand_requests(pack, seed=42, requests=20)
    c = expand_requests(pack, seed=99, requests=20)
    assert len(a) == 20
    assert [x["scenario_id"] for x in a] == [x["scenario_id"] for x in b]
    assert [x["prompt"] for x in a] == [x["prompt"] for x in b]
    assert [x["scenario_id"] for x in a] != [x["scenario_id"] for x in c]


def test_mixed_requests_drives_generate_count():
    """CLI/UI --requests N expands mixed packs to N (generate_count is default only)."""
    pack = load_pack("enterprise-mixed")
    assert int(pack.get("generate_count") or 0) == 40
    defaulted = expand_requests(pack, seed=7)
    assert len(defaulted) == 40
    expanded = expand_requests(pack, seed=7, requests=200)
    assert len(expanded) == 200
    # Same seed ⇒ shared prefix with default run
    assert [x["scenario_id"] for x in expanded[:40]] == [x["scenario_id"] for x in defaulted]
    # Alias max_requests still works
    via_alias = expand_requests(pack, seed=7, max_requests=55)
    assert len(via_alias) == 55


def test_fixed_pack_cycles_to_requests():
    """Fixed packs repeat scenarios until target N for long Grafana demos."""
    pack = load_pack("smoke")
    once = expand_requests(pack)
    n_base = len(once)
    assert 8 <= n_base <= 12
    target = n_base * 3 + 2
    cycled = expand_requests(pack, requests=target)
    assert len(cycled) == target
    # Cycles scenario list in order
    for i, spec in enumerate(cycled):
        assert spec["scenario_id"] == once[i % n_base]["scenario_id"]
    # Prompt variants rotate stably when a scenario has multiple prompts
    by_id = {s["id"]: s for s in pack["scenarios"]}
    for i, spec in enumerate(cycled):
        sc = by_id[spec["scenario_id"]]
        prompts = (sc.get("request") or {}).get("prompts")
        if prompts and len(prompts) > 1:
            assert spec["prompt"] == prompts[i % len(prompts)]


def test_plan_respects_target_requests():
    plan = DemoRunner(mock=True).plan("enterprise-mixed", seed=1, requests=75)
    assert plan["planned_requests"] == 75
    plan_smoke = DemoRunner(mock=True).plan("smoke", requests=50)
    assert plan_smoke["planned_requests"] == 50



def test_observability_metadata_to_instrumentor():
    instr = DemoInstrumentor()
    span = instr.emit_request(
        demo_run_id="run-1",
        scenario_id="interactive-coding",
        request_id="req-1",
        use_case="coding-assistant",
        policy="2.4",
        serving_pattern="interactive",
        lifecycle="production",
        model="openai/gpt-oss-120b",
        compute="MI300X",
        compute_family="instinct",
        endpoint="gpt-oss-120b-coding",
        fallback_used=False,
        validation_status="PASS",
    )
    assert span.attributes["demo_run_id"] == "run-1"
    assert instr.has_expected_attributes("req-1")
    text = instr.prometheus_text()
    assert "token_factory_demo_requests_total" in text
    assert "req-1" not in text  # no request UUID labels
    assert 'lifecycle="production"' in text


def test_metrics_server_exposes_prometheus_text(tmp_path, monkeypatch):
    from token_factory.demo.metrics_server import (
        start_metrics_server,
        stop_metrics_server,
        metrics_endpoint_url,
    )
    import urllib.request

    monkeypatch.setenv("TF_GENERATED_DIR", str(tmp_path))
    stop_metrics_server()
    listen = start_metrics_server(port=19108)
    assert listen is not None
    instr = DemoInstrumentor()
    from token_factory.demo import observability as obs

    prev = obs.INSTRUMENTOR
    obs.INSTRUMENTOR = instr
    try:
        instr.emit_request(
            demo_run_id="run-1",
            scenario_id="interactive-coding",
            request_id="req-metrics",
            use_case="coding-assistant",
            policy="2.4",
            serving_pattern="interactive",
            lifecycle="production",
            model="openai/gpt-oss-120b",
            compute="MI300X",
            compute_family="instinct",
            endpoint="gpt-oss-120b-coding",
            fallback_used=False,
            validation_status="PASS",
        )
        with urllib.request.urlopen(metrics_endpoint_url(port=19108), timeout=2) as resp:
            body = resp.read().decode()
        assert "token_factory_demo_requests_total" in body
        assert "req-metrics" not in body
        snap = tmp_path / "demo-metrics.prom"
        assert snap.is_file()
        assert "token_factory_demo_requests_total" in snap.read_text()
    finally:
        obs.INSTRUMENTOR = prev
        stop_metrics_server()


def test_smoke_run_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("TF_GENERATED_DIR", str(tmp_path))
    instr = DemoInstrumentor()
    runner = DemoRunner(mock=True, instrumentor=instr)
    run = runner.run("smoke", mock=True, ci=True, persist=True)
    assert run.validation_summary["requests"] >= 8
    assert run.policy_ok()
    assert any(r.telemetry.get("demo_run_id") == run.id for r in run.requests)
    art = Path(run.meta["artifact"])
    assert art.is_file()
    payload = json.loads(art.read_text())
    assert payload["run_id"] == run.id
    assert "requests" in payload


def test_fallback_injection_sets_flag():
    runner = DemoRunner(mock=True)
    run = runner.run(
        "fallback",
        mock=True,
        inject=["preferred-endpoint-unavailable"],
        persist=False,
    )
    assert run.validation_summary["requests"] >= 1
    # At least one request should record fallback when preferred is forced down
    assert any((r.actual or {}).get("fallback_used") for r in run.requests) or run.policy_ok()


def test_ci_policy_ok_ignores_latency():
    runner = DemoRunner(mock=True)
    run = runner.run("smoke", mock=True, ci=True, persist=False)
    # Attach fake slow latency — must not affect policy_ok
    for r in run.requests:
        r.telemetry["duration_ms"] = 999_999
        r.telemetry["ttft_ms"] = 999_999
    assert run.policy_ok() is True


def test_plan_smoke():
    plan = DemoRunner(mock=True).plan("smoke")
    assert plan["pack_id"] == "smoke"
    assert plan["planned_requests"] >= 8
    assert plan["scenarios"]


def test_docs_and_code_ban_benchmark_framing():
    """New demo docs/UI must not present as a benchmark portal."""
    # Affirmative banned framing (negated mentions in anti-statements are OK in docs)
    banned_affirmative = [
        "hardware shootout",
        "performance winner",
        "tokens/sec comparison portal",
        "gpu benchmark",
        "cpu vs gpu benchmark",
    ]
    paths = [
        ROOT / "docs" / "automated-demo.md",
        ROOT / "ui" / "views" / "automated_demo.py",
        ROOT / "src" / "token_factory" / "demo" / "runner.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in banned_affirmative:
            assert phrase not in text, f"{phrase!r} found in {path}"
    docs = (ROOT / "docs" / "automated-demo.md").read_text(encoding="utf-8")
    assert "not a benchmark framework" in docs.lower()
    # Must not market itself as a leaderboard product
    assert "leaderboard" not in docs.lower()


def test_pack_yaml_no_benchmark_portal_language():
    for name in ("smoke", "executive", "enterprise-mixed"):
        raw = (scenarios_dir() / f"{name}.yaml").read_text(encoding="utf-8").lower()
        assert "leaderboard" not in raw
        assert "hardware shootout" not in raw or "not a hardware shootout" in raw
        assert "performance winner" not in raw
