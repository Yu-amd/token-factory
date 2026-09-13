"""Smoke integration — mocked adapters (CI without cluster)."""

from __future__ import annotations

from token_factory.demo.observability import DemoInstrumentor
from token_factory.demo.runner import DemoRunner


def test_smoke_integration_mocked_adapters():
    """Deterministic smoke covering coding / general / batch / multimodal / fallback."""
    instr = DemoInstrumentor()
    runner = DemoRunner(mock=True, instrumentor=instr)
    run = runner.run(
        "smoke",
        mock=True,
        ci=True,
        inject=["preferred-endpoint-unavailable"],
        persist=False,
    )
    assert run.validation_summary["requests"] >= 8
    assert run.policy_ok()

    scenarios = {r.scenario_id for r in run.requests}
    assert "interactive-coding" in scenarios
    assert "enterprise-chat" in scenarios
    assert "batch-summarization" in scenarios
    assert "local-multimodal" in scenarios

    # Telemetry attributes reached instrumentation layer
    assert len(instr.spans) >= 8
    assert instr.get_counter("token_factory_demo_requests_total")

    # Canonical vs runtime fields present
    coding = next(r for r in run.requests if r.scenario_id == "interactive-coding")
    assert coding.actual.get("canonical_preferred") is not None or coding.actual.get(
        "runtime_selected"
    )
    assert coding.validation.get("classification") in ("PASS", "WARN", "N/A")
    assert coding.validation.get("route") in ("PASS", "WARN")


def test_executive_pack_story_sequence():
    run = DemoRunner(mock=True).run("executive", mock=True, persist=False)
    ids = [r.scenario_id for r in run.requests]
    assert ids[0].startswith("exec-coding")
    assert any("fallback" in i for i in ids)
    assert any("lifecycle" in i for i in ids)
    assert run.policy_ok()


def test_observability_pack_emits_attributes():
    instr = DemoInstrumentor()
    run = DemoRunner(mock=True, instrumentor=instr).run(
        "observability", mock=True, persist=False
    )
    assert run.policy_ok()
    for r in run.requests:
        assert r.telemetry.get("demo_run_id") == run.id
        assert r.telemetry.get("scenario_id")
        assert r.telemetry.get("request_id")
        assert instr.has_expected_attributes(r.request_id)
