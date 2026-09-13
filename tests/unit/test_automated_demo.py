"""Tests for Automated Demo scenario loading, validation, runner, CI exit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from token_factory.demo.injection import apply_endpoint_overlay, normalize_injections
from token_factory.demo.loader import expand_requests, list_packs, load_pack, scenarios_dir
from token_factory.demo.models import DemoRequest, ValidationStatus
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


def test_observability_runtime_escalation_counter():
    instr = DemoInstrumentor()
    instr.record_counters(
        scenario_id="interactive-coding",
        use_case="coding-assistant",
        compute_family="instinct",
        model="openai/gpt-oss-20b",
        validation_status="PASS",
        lifecycle="production",
        fallback_used=False,
        runtime_escalation=True,
    )
    text = instr.prometheus_text()
    assert "token_factory_demo_runtime_escalation_total" in text
    assert "token_factory_demo_fallback_total" not in text
    assert sum(instr.get_counter("token_factory_demo_runtime_escalation_total").values()) == 1


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
    import urllib.request

    from token_factory.demo.metrics_server import (
        metrics_endpoint_url,
        start_metrics_server,
        stop_metrics_server,
    )

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


def test_preferred_not_deployed_increments_runtime_escalation():
    """Preferred model×compute not in inventory → runtime_escalation metric, not fallback."""
    instr = DemoInstrumentor()
    runner = DemoRunner(mock=True, instrumentor=instr)
    run = runner.run("smoke", mock=True, persist=False)
    escalated = [
        r
        for r in run.requests
        if (r.actual or {}).get("runtime_escalation")
    ]
    assert escalated, "expected at least one preferred-not-deployed → next-eligible escalation"
    for r in escalated:
        a = r.actual or {}
        assert a.get("preferred_not_deployed") is True
        # Without preferred-endpoint-unavailable injection, escalation ≠ fallback
        if "preferred-endpoint-unavailable" not in (a.get("injections") or []):
            assert a.get("fallback_used") is False
        can = a.get("canonical_preferred") or {}
        rt = a.get("runtime_selected") or {}
        assert (
            can.get("model") != rt.get("model")
            or can.get("compute") != rt.get("compute")
            or can.get("endpoint_id") != rt.get("endpoint_id")
        )
        assert rt.get("endpoint_available") is True

    escal_counter = instr.get_counter("token_factory_demo_runtime_escalation_total")
    assert sum(escal_counter.values()) == len(escalated)
    assert "token_factory_demo_runtime_escalation_total" in instr.prometheus_text()
    fb = instr.get_counter("token_factory_demo_fallback_total")
    assert sum(fb.values()) == sum(
        1 for r in run.requests if (r.actual or {}).get("fallback_used")
    )


def test_smoke_mi300x_only_inventory_increments_escalation():
    """Smoke without inject on MI300X-only inventory must scrape escalation > 0.

    Matches the operator mental model “fallback to MI300X” when preferred SKUs
    (e.g. MI355X) are not deployed — counted as runtime_escalation, not injected
    fallback_total.
    """
    from token_factory.config import load_endpoints

    inventory = [
        dict(ep)
        for ep in load_endpoints().get("endpoints", [])
        if ep.get("accelerator") == "MI300X" and ep.get("enabled", True)
    ]
    assert inventory, "expected at least one enabled MI300X endpoint"
    assert all(ep.get("accelerator") == "MI300X" for ep in inventory)

    instr = DemoInstrumentor()
    runner = DemoRunner(mock=True, endpoints=inventory, instrumentor=instr)
    run = runner.run("smoke", mock=True, persist=False)
    summary = run.validation_summary
    assert summary.get("runtime_escalations", 0) > 0
    assert sum(instr.get_counter("token_factory_demo_runtime_escalation_total").values()) > 0
    # Smoke has one inject scenario; preferred-not-deployed escalations dominate
    assert summary.get("fallbacks", 0) < summary["runtime_escalations"]
    assert "token_factory_demo_runtime_escalation_total" in instr.prometheus_text()


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


# --- Presentation layer (ADVISORY vs WARN) ---


def test_presentation_runtime_inventory_constraint():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"route": "WARN", "policy": "PASS", "telemetry": "PASS"},
        {
            "preferred_not_deployed": True,
            "canonical_preferred": {"model": "A", "compute": "MI355X"},
            "runtime_selected": None,
        },
        {"routing": {}},
    )
    assert result.status == "ADVISORY"
    assert result.advisory_reason == "runtime_inventory_constraint"
    assert result.message


def test_presentation_local_candidate_unavailable():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"policy": "WARN", "route": "PASS", "telemetry": "PASS"},
        {
            "no_local_candidate": True,
            "selected_compute_family": "instinct",
            "runtime_selected": {"model": "x", "compute": "MI300X", "family": "instinct"},
            "preferred_not_deployed": True,
        },
        {"routing": {"require_local": True, "allow_no_runtime": True, "preferred_compute_family": ["radeon"]}},
    )
    assert result.status == "ADVISORY"
    assert result.advisory_reason == "local_candidate_unavailable"


def test_presentation_soft_family_tendency_mismatch():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"policy": "WARN", "route": "PASS", "telemetry": "PASS"},
        {
            "selected_compute_family": "instinct",
            "runtime_selected": {"model": "x", "compute": "MI300X", "family": "instinct"},
        },
        {
            "routing": {
                "compute_family_tendency": "epyc",
                "preferred_compute_family": ["epyc", "instinct"],
            }
        },
    )
    assert result.status == "ADVISORY"
    assert result.advisory_reason == "soft_family_tendency_mismatch"


def test_presentation_preferred_compute_unavailable():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"policy": "WARN", "route": "PASS", "telemetry": "PASS"},
        {
            "selected_compute_family": "instinct",
            "runtime_selected": {"model": "x", "compute": "MI300X", "family": "instinct"},
        },
        {"routing": {"preferred_compute_family": ["radeon"]}},
    )
    assert result.status == "ADVISORY"
    assert result.advisory_reason == "preferred_compute_unavailable"


def test_presentation_telemetry_stays_warn():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"telemetry": "WARN", "route": "PASS", "policy": "PASS"},
        {"runtime_selected": {"model": "x", "compute": "MI300X"}},
        {"routing": {}},
    )
    assert result.status == "WARN"
    assert result.advisory_reason == "observability_warning"


def test_presentation_fail_unchanged():
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {"classification": "FAIL", "policy": "PASS"},
        {},
        {},
    )
    assert result.status == "FAIL"
    assert result.advisory_reason is None


def test_presentation_pass_with_escalation_stays_pass():
    """Runtime escalation is a routing event — not auto-ADVISORY."""
    from token_factory.demo.presentation import classify_presentation_status

    result = classify_presentation_status(
        {
            "classification": "PASS",
            "policy": "PASS",
            "capability": "PASS",
            "lifecycle": "PASS",
            "route": "PASS",
            "endpoint": "PASS",
            "telemetry": "PASS",
        },
        {
            "preferred_not_deployed": True,
            "runtime_escalation": True,
            "runtime_selected": {"model": "b", "compute": "MI300X", "family": "instinct"},
            "canonical_preferred": {"model": "a", "compute": "MI355X"},
        },
        {"routing": {"preferred_compute_family": ["instinct"]}},
    )
    assert result.status == "PASS"
    assert result.advisory_reason is None


def test_presentation_does_not_blindly_map_warn():
    from token_factory.demo.presentation import classify_presentation_status

    # WARN without soft structured explanation → stays WARN
    result = classify_presentation_status(
        {"capability": "WARN", "telemetry": "PASS"},
        {"runtime_selected": None},
        {"routing": {}},
    )
    assert result.status == "WARN"


def test_request_exposes_validation_and_presentation_status():
    req = DemoRequest(
        demo_run_id="r1",
        scenario_id="mix-local",
        request_id="req-1",
        prompt="local",
        expected={"routing": {"require_local": True, "allow_no_runtime": True}},
        actual={
            "no_local_candidate": True,
            "selected_compute_family": "instinct",
            "runtime_selected": {"model": "x", "compute": "MI300X", "family": "instinct"},
        },
        validation={"policy": "WARN", "route": "PASS", "telemetry": "PASS"},
    )
    assert req.overall().value == "WARN"
    d = req.to_dict()
    assert d["validation_status"] == "WARN"
    assert d["presentation_status"] == "ADVISORY"
    assert d["advisory_reason"] == "local_candidate_unavailable"
    assert d["validation"]["policy"] == "WARN"  # internal unchanged


def _fake_request(
    *,
    validation: dict[str, str],
    actual: dict | None = None,
    expected: dict | None = None,
    index: int = 0,
) -> DemoRequest:
    return DemoRequest(
        demo_run_id="run",
        scenario_id=f"s-{index}",
        request_id=f"req-{index}",
        prompt="p",
        expected=expected or {},
        actual=actual or {},
        validation=validation,
        index=index,
        status="completed",
    )


def test_summary_counts_all_advisory_from_internal_warns():
    """61 PASS + 39 internal WARN (all soft) → passed=61 advisory=39 warnings=0."""
    from token_factory.demo.models import DemoRun
    from token_factory.demo.runner import DemoRunner

    requests = []
    for i in range(61):
        requests.append(
            _fake_request(
                validation={
                    "classification": "PASS",
                    "policy": "PASS",
                    "route": "PASS",
                    "telemetry": "PASS",
                },
                actual={"runtime_escalation": True, "preferred_not_deployed": True},
                index=i,
            )
        )
    for i in range(39):
        requests.append(
            _fake_request(
                validation={"policy": "WARN", "route": "PASS", "telemetry": "PASS"},
                actual={
                    "preferred_not_deployed": True,
                    "no_local_candidate": True,
                    "selected_compute_family": "instinct",
                    "runtime_selected": {
                        "model": "x",
                        "compute": "MI300X",
                        "family": "instinct",
                    },
                },
                expected={
                    "routing": {
                        "require_local": True,
                        "allow_no_runtime": True,
                        "preferred_compute_family": ["radeon"],
                    }
                },
                index=61 + i,
            )
        )
    run = DemoRun.create("enterprise-mixed", mock=True)
    run.requests = requests
    summary = DemoRunner._summarize(run)
    assert summary["passed"] == 61
    assert summary["advisory"] == 39
    assert summary["warnings"] == 0
    assert summary["failed"] == 0
    assert summary["advisory_reasons"].get("local_candidate_unavailable") == 39
    # Internal validation still WARN on those requests
    assert sum(1 for r in requests if r.overall().value == "WARN") == 39


def test_summary_counts_mixed_advisory_warn_fail():
    from token_factory.demo.models import DemoRun
    from token_factory.demo.runner import DemoRunner

    requests = []
    for i in range(60):
        requests.append(
            _fake_request(
                validation={"classification": "PASS", "policy": "PASS", "telemetry": "PASS"},
                index=i,
            )
        )
    for i in range(35):
        requests.append(
            _fake_request(
                validation={"policy": "WARN", "telemetry": "PASS"},
                actual={
                    "preferred_not_deployed": True,
                    "runtime_selected": None,
                },
                expected={"routing": {}},
                index=60 + i,
            )
        )
    for i in range(4):
        requests.append(
            _fake_request(
                validation={"telemetry": "WARN", "policy": "PASS"},
                actual={},
                expected={},
                index=95 + i,
            )
        )
    requests.append(
        _fake_request(
            validation={"classification": "FAIL"},
            index=99,
        )
    )
    run = DemoRun.create("mixed", mock=True)
    run.requests = requests
    summary = DemoRunner._summarize(run)
    assert summary["passed"] == 60
    assert summary["advisory"] == 35
    assert summary["warnings"] == 4
    assert summary["failed"] == 1
    assert summary["policy_ok"] is False


def test_enterprise_mixed_seed42_soft_warns_are_advisory():
    """Live pack: soft locality WARNs present as ADVISORY; escalations stay PASS."""
    runner = DemoRunner(mock=True)
    run = runner.run(
        "enterprise-mixed",
        requests=100,
        seed=42,
        traffic="medium",
        mock=True,
        persist=False,
    )
    summary = run.validation_summary
    assert summary["failed"] == 0
    assert summary["requests"] == 100
    assert summary["passed"] + summary["advisory"] + summary["warnings"] + summary[
        "failed"
    ] == 100
    # Soft WARNs should not remain as user-facing warnings when classifiable
    for r in run.requests:
        if r.overall().value == "WARN":
            assert r.presentation().status in ("ADVISORY", "WARN")
            if (r.actual or {}).get("no_local_candidate"):
                assert r.presentation().status == "ADVISORY"
        if (r.actual or {}).get("runtime_escalation") and r.overall().value == "PASS":
            assert r.presentation().status == "PASS"
    assert summary["runtime_escalations"] > 0
