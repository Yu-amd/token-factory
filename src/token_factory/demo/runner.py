"""Automated Demo runner — sequential / bounded concurrency policy validation.

Reuses RecommendationEngine + endpoint inventory. Failure injection is an overlay
only; canonical AMD policy is never mutated. Latency is telemetry, never a
comparative claim.
"""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from token_factory.config import load_endpoints
from token_factory.demo.adapters import MockClassifyAdapter, resolve_adapters
from token_factory.demo.injection import (
    apply_endpoint_overlay,
    effective_lifecycle,
    mark_preferred_unavailable,
    normalize_injections,
)
from token_factory.demo.loader import expand_requests, load_pack
from token_factory.demo.models import DemoRequest, DemoRun, ValidationStatus, new_id, utc_now
from token_factory.demo.normalize import compute_family_of, normalize_label
from token_factory.demo.observability import get_instrumentor
from token_factory.demo.persist import persist_run
from token_factory.demo.validation import validate_request
from token_factory.routing_matrix import RecommendationEngine

MAX_REQUESTS = 8000
MAX_CONCURRENCY = 10

TRAFFIC_CONCURRENCY = {
    "sequential": 1,
    "low": 1,
    "light": 2,
    "medium": 4,
    "mixed": 4,
    "high": 8,
}


ProgressCallback = Callable[[DemoRequest, DemoRun], None]


def _route_identity_differs(
    left: dict[str, Any] | None, right: dict[str, Any] | None
) -> bool:
    """True when model / compute / endpoint_id differ between two route dicts."""
    if not left or not right:
        return False
    return (
        left.get("model") != right.get("model")
        or left.get("compute") != right.get("compute")
        or left.get("endpoint_id") != right.get("endpoint_id")
    )


class DemoRunner:
    def __init__(
        self,
        *,
        engine: RecommendationEngine | None = None,
        endpoints: list[dict[str, Any]] | None = None,
        mock: bool | None = None,
        instrumentor: Any | None = None,
    ):
        self.engine = engine or RecommendationEngine()
        self.base_endpoints = endpoints if endpoints is not None else load_endpoints().get(
            "endpoints", []
        )
        self.mock = mock
        self.instrumentor = instrumentor or get_instrumentor()

    def plan(self, pack_id: str, *, seed: int | None = None, requests: int | None = None) -> dict[str, Any]:
        pack = load_pack(pack_id)
        target = min(int(requests), MAX_REQUESTS) if requests is not None else None
        specs = expand_requests(pack, requests=target, seed=seed)
        return {
            "pack_id": pack["id"],
            "display_name": pack.get("display_name"),
            "description": pack.get("description"),
            "coverage": pack.get("coverage") or {},
            "scenario_count": len(pack.get("scenarios") or []),
            "planned_requests": len(specs),
            "scenarios": [
                {
                    "id": s["scenario_id"],
                    "display_name": s["display_name"],
                    "use_case": s.get("use_case_hint")
                    or (s.get("expected") or {}).get("classification", {}).get("use_case"),
                    "serving_pattern": s.get("serving_pattern"),
                    "preferred_compute_family": (
                        (s.get("expected") or {}).get("routing") or {}
                    ).get("preferred_compute_family")
                    or (s.get("expected") or {}).get("routing", {}).get("compute_family_tendency"),
                    "lifecycle": (s.get("policy_context") or {}).get("lifecycle"),
                    "inject": s.get("inject") or [],
                    "prompt_preview": (s.get("prompt") or "")[:120],
                }
                for s in specs
            ],
        }

    def run(
        self,
        pack_id: str,
        *,
        lifecycle: str = "production",
        traffic: str = "sequential",
        requests: int | None = None,
        concurrency: int | None = None,
        seed: int | None = None,
        inject: list[str] | None = None,
        ci: bool = False,
        mock: bool | None = None,
        on_progress: ProgressCallback | None = None,
        persist: bool = True,
    ) -> DemoRun:
        pack = load_pack(pack_id)
        injections = normalize_injections(inject or [])
        life = effective_lifecycle(lifecycle, injections)
        traffic_key = (traffic or "sequential").lower()
        conc = concurrency if concurrency is not None else TRAFFIC_CONCURRENCY.get(traffic_key, 1)
        conc = max(1, min(int(conc), MAX_CONCURRENCY))
        target = min(int(requests), MAX_REQUESTS) if requests is not None else None

        use_mock = self.mock if mock is None else mock
        # CI defaults to mock when services unavailable
        if ci and use_mock is None:
            use_mock = None  # auto

        run = DemoRun.create(
            pack_id,
            lifecycle_mode=life,
            traffic_profile=traffic_key,
            seed=seed,
            concurrency=conc,
            injections=injections,
            mock=bool(use_mock) if use_mock is not None else False,
            ci=ci,
        )
        run.coverage = pack.get("coverage") or {}
        run.meta = {
            "policy_version": (self.engine.policy.get("metadata") or {})
            .get("amd_routing_policy", {})
            .get("version")
            or self.engine.bundle.get("use_cases", {}).get("metadata", {}).get("policy_version"),
            "anti_benchmark": (
                "Automated Demo validates routing-policy execution and observability. "
                "It is not a benchmark framework."
            ),
        }

        specs = expand_requests(pack, requests=target, seed=seed)
        # Pre-build request shells
        for spec in specs:
            run.requests.append(
                DemoRequest(
                    demo_run_id=run.id,
                    scenario_id=spec["scenario_id"],
                    request_id=new_id(),
                    prompt=spec["prompt"],
                    expected=spec.get("expected") or {},
                    display_name=spec.get("display_name"),
                    index=spec.get("index", 0),
                )
            )

        def _execute(idx: int) -> DemoRequest:
            spec = specs[idx]
            req = run.requests[idx]
            return self._run_one(run, req, spec, pack=pack, use_mock=use_mock)

        if conc <= 1:
            for i in range(len(specs)):
                req = _execute(i)
                run.requests[i] = req
                if on_progress:
                    on_progress(req, run)
        else:
            with ThreadPoolExecutor(max_workers=conc) as pool:
                futures = {pool.submit(_execute, i): i for i in range(len(specs))}
                for fut in as_completed(futures):
                    i = futures[fut]
                    req = fut.result()
                    run.requests[i] = req
                    if on_progress:
                        on_progress(req, run)

        run.completed_at = utc_now()
        run.validation_summary = self._summarize(run)
        run.distributions = self._distributions(run)
        # Resolve whether we actually used mocks
        run.mock = any((r.actual or {}).get("mock") for r in run.requests)
        if persist:
            path = persist_run(run)
            run.meta["artifact"] = str(path)
        return run

    def _run_one(
        self,
        run: DemoRun,
        req: DemoRequest,
        spec: dict[str, Any],
        *,
        pack: dict[str, Any],
        use_mock: bool | None,
    ) -> DemoRequest:
        req.status = "running"
        req.started_at = utc_now()
        t0 = time.perf_counter()
        local_inject = normalize_injections(list(run.injections) + list(spec.get("inject") or []))
        ctx = spec.get("policy_context") or {}
        life = effective_lifecycle(
            ctx.get("lifecycle") or run.lifecycle_mode, local_inject
        )
        serving = spec.get("serving_pattern") or "interactive"
        objective = spec.get("objective")
        use_case = (
            spec.get("use_case_hint")
            or (spec.get("expected") or {}).get("classification", {}).get("use_case")
            or "enterprise-chat"
        )
        data_locality = bool(
            ctx.get("locality") in ("local", "radeon", "workstation")
            or (spec.get("expected") or {}).get("routing", {}).get("require_local")
        )
        utilization = ctx.get("traffic") or (
            "high" if run.traffic_profile == "high" else "medium"
        )

        try:
            classify_adapter, chat_adapter = resolve_adapters(
                mock=use_mock, use_case_hint=use_case
            )
            # Prefer hint-aware mock classify
            if isinstance(classify_adapter, MockClassifyAdapter):
                classified = classify_adapter.classify(
                    req.prompt, use_case_hint=use_case
                )
            else:
                try:
                    classified = classify_adapter.classify(
                        req.prompt, use_case_hint=use_case
                    )
                except Exception as exc:
                    # Soft-fallback to mock classify for resilience
                    classified = MockClassifyAdapter(hint=use_case).classify(
                        req.prompt, use_case_hint=use_case
                    )
                    classified["live_error"] = str(exc)[:200]

            category = (
                (classified.get("classification") or {}).get("category")
                or classified.get("routing_decision")
                or use_case
            )
            classify_ms = classified.get("_classify_ms")

            endpoints = apply_endpoint_overlay(self.base_endpoints, local_inject)

            # Canonical recommendation (full inventory without preferred-unavailable)
            base_for_canonical = apply_endpoint_overlay(
                self.base_endpoints,
                [i for i in local_inject if i != "preferred-endpoint-unavailable"],
            )
            sim_full = self.engine.simulate_route(
                use_case,
                objective=objective,
                utilization=utilization,
                endpoints=base_for_canonical,
                lifecycle_mode=life,
                data_locality=data_locality,
                serving_pattern=serving,
            )
            canonical = (sim_full.get("amd_recommendation") or [None])[0]
            preferred_not_deployed = False
            if canonical and not canonical.get("endpoint_available"):
                preferred_not_deployed = True

            # Apply preferred-unavailable after we know the preferred candidate
            runtime_endpoints = endpoints
            fallback_used = False
            if "preferred-endpoint-unavailable" in local_inject:
                runtime_endpoints = mark_preferred_unavailable(endpoints, canonical)
                fallback_used = True

            sim = self.engine.simulate_route(
                use_case,
                objective=objective,
                utilization=utilization,
                endpoints=runtime_endpoints,
                lifecycle_mode=life,
                data_locality=data_locality,
                serving_pattern=serving,
            )
            runtime = sim.get("selected_runtime_route")
            if not runtime and sim.get("amd_recommendation"):
                # No deployed endpoint — still surface top policy candidate for validation
                top = sim["amd_recommendation"][0]
                runtime = dict(top)
                runtime["endpoint_available"] = False
                runtime["_synthetic"] = True

            # Injected preferred-endpoint-unavailable → fallback_used when selection differs
            if "preferred-endpoint-unavailable" in local_inject and _route_identity_differs(
                canonical, runtime
            ):
                fallback_used = True

            # Preferred not deployed → next eligible deployed route (not injection)
            runtime_escalation = False
            if preferred_not_deployed and _route_identity_differs(canonical, runtime):
                # Require a real deployed runtime candidate (not synthetic top-of-list)
                if runtime and runtime.get("endpoint_available") and not runtime.get(
                    "_synthetic"
                ):
                    runtime_escalation = True

            model_id = (runtime or {}).get("model") or (canonical or {}).get("model")
            compute_id = (runtime or {}).get("compute") or (canonical or {}).get("compute")
            family = compute_family_of(
                compute_id, (runtime or canonical or {}).get("family")
            )
            endpoint_id = (runtime or {}).get("endpoint_id")

            # Model capability lookup
            model_meta = self.engine.models.get(model_id or "") or {}
            model_caps = model_meta.get("capabilities") or {}

            # Multimodal mismatch detection
            required_caps = (
                (spec.get("expected") or {}).get("capabilities") or {}
            ).get("required") or []
            text_only_for_vision = False
            if any(c in ("vision", "multimodal") for c in required_caps):
                if model_caps.get("vision") is False:
                    text_only_for_vision = True

            # Optional chat call (mock or live) — short completion
            chat_meta: dict[str, Any] = {}
            try:
                chat_body = chat_adapter.complete(
                    req.prompt,
                    model=None,  # virtual model through gateway; mock ignores
                    max_tokens=32,
                )
                chat_meta = {
                    "chat_model": chat_body.get("model"),
                    "duration_ms": chat_body.get("_duration_ms"),
                    "mock_chat": bool(chat_body.get("mock")),
                }
            except Exception as exc:
                chat_meta = {"chat_error": str(exc)[:200]}

            life_excl = sim.get("lifecycle_exclusions") or []
            tp_excluded = any(
                e.get("lifecycle") in ("tech-preview", "preview") for e in life_excl
            )

            reason = sim.get("explanation") or ""
            if preferred_not_deployed and runtime and canonical:
                if canonical.get("model") != runtime.get("model") or canonical.get(
                    "compute"
                ) != runtime.get("compute"):
                    reason = "preferred candidate not deployed; highest-ranked healthy deployed eligible candidate"

            actual = {
                "classified_use_case": use_case,
                "classification_category": category,
                "routing_decision": classified.get("routing_decision"),
                "classification": classified.get("classification"),
                "confidence": (classified.get("classification") or {}).get("confidence"),
                "use_case_hint": use_case,
                "lifecycle_mode": life,
                "serving_pattern": sim.get("serving_pattern") or serving,
                "objective": sim.get("objective") or objective,
                "policy_version": sim.get("policy_version"),
                "canonical_preferred": canonical,
                "runtime_selected": runtime,
                "preferred_not_deployed": preferred_not_deployed,
                "canonical_vs_runtime_reason": reason,
                "selected_model": model_id,
                "selected_compute": compute_id,
                "selected_compute_family": family,
                "selected_endpoint": endpoint_id,
                "selected_lifecycle": (runtime or {}).get("lifecycle"),
                "fallback_used": fallback_used,
                "runtime_escalation": runtime_escalation,
                "lifecycle_exclusions_count": len(life_excl),
                "tp_excluded": tp_excluded,
                "model_capabilities": model_caps,
                "text_only_for_vision": text_only_for_vision,
                "no_local_candidate": bool(data_locality and family != "radeon"),
                "local_selected": family == "radeon",
                "mock": bool(classified.get("mock")) or bool(chat_meta.get("mock_chat")),
                "classify_ms": classify_ms,
                "explanation": reason,
                "chat": chat_meta,
                "injections": local_inject,
            }

            duration_ms = (time.perf_counter() - t0) * 1000
            tel_attrs = {
                "demo_run_id": run.id,
                "scenario_id": req.scenario_id,
                "request_id": req.request_id,
                "classified_use_case": use_case,
                "selected_model": model_id,
                "selected_compute": compute_id,
                "selected_endpoint": endpoint_id,
                "policy_profile": run.meta.get("policy_version"),
                "serving_pattern": serving,
                "lifecycle": life,
                "fallback_used": fallback_used,
                "runtime_escalation": runtime_escalation,
            }
            actual["telemetry"] = tel_attrs

            # Span first (telemetry attribute check), counters after validation status is known.
            span = self.instrumentor.start_span("token_factory.demo.request", **tel_attrs)
            if duration_ms is not None:
                span.set("duration_ms", duration_ms)
            if classify_ms is not None:
                span.set("classify_ms", float(classify_ms))
            telemetry_ok = self.instrumentor.has_expected_attributes(req.request_id)

            observability_pack = pack.get("id") == "observability" or bool(
                (spec.get("validation") or {}).get("telemetry_strict")
            )
            validation = validate_request(
                expected=spec.get("expected") or {},
                actual=actual,
                validation_flags=spec.get("validation"),
                telemetry_ok=telemetry_ok,
                observability_pack=observability_pack,
            )
            req.actual = actual
            req.validation = validation
            overall = req.overall().value
            self.instrumentor.record_counters(
                scenario_id=req.scenario_id,
                use_case=use_case,
                compute_family=family,
                model=model_id,
                validation_status=overall,
                lifecycle=life,
                fallback_used=fallback_used,
                runtime_escalation=runtime_escalation,
            )
            req.telemetry = {
                **tel_attrs,
                "duration_ms": round(duration_ms, 2),
                "span_attributes": span.attributes,
            }
            req.actual["validation_overall"] = overall
            req.status = "completed"
            req.completed_at = utc_now()
            return req

        except Exception as exc:
            req.status = "error"
            req.error = str(exc)[:400]
            req.actual = {"error": req.error, "mock": True}
            req.validation = {d: ValidationStatus.FAIL.value for d in (
                "classification", "policy", "capability", "lifecycle", "route", "endpoint"
            )}
            req.validation["telemetry"] = ValidationStatus.WARN.value
            req.completed_at = utc_now()
            return req

    @staticmethod
    def _summarize(run: DemoRun) -> dict[str, Any]:
        total = len(run.requests)
        passed = warn = failed = 0
        fallbacks = 0
        runtime_escalations = 0
        dim_counts: dict[str, Counter[str]] = {
            d: Counter() for d in (
                "classification", "policy", "capability", "lifecycle", "route", "endpoint", "telemetry"
            )
        }
        for r in run.requests:
            overall = r.overall()
            if overall == ValidationStatus.PASS:
                passed += 1
            elif overall == ValidationStatus.WARN:
                warn += 1
            elif overall == ValidationStatus.FAIL:
                failed += 1
            if (r.actual or {}).get("fallback_used"):
                fallbacks += 1
            if (r.actual or {}).get("runtime_escalation"):
                runtime_escalations += 1
            for d, v in (r.validation or {}).items():
                if d in dim_counts:
                    dim_counts[d][v] += 1
        return {
            "requests": total,
            "completed": sum(1 for r in run.requests if r.status == "completed"),
            "passed": passed,
            "warnings": warn,
            "failed": failed,
            "fallbacks": fallbacks,
            "runtime_escalations": runtime_escalations,
            "policy_ok": run.policy_ok(),
            "dimensions": {k: dict(v) for k, v in dim_counts.items()},
        }

    @staticmethod
    def _distributions(run: DemoRun) -> dict[str, Any]:
        """Routing / model / use-case distributions — coverage, not performance."""
        use_cases: Counter[str] = Counter()
        models: Counter[str] = Counter()
        families: Counter[str] = Counter()
        serving: Counter[str] = Counter()
        for r in run.requests:
            a = r.actual or {}
            use_cases[normalize_label(a.get("classified_use_case") or a.get("use_case_hint") or "unknown")] += 1
            models[str(a.get("selected_model") or "none")] += 1
            families[str(a.get("selected_compute_family") or "unknown")] += 1
            serving[str(a.get("serving_pattern") or "unknown")] += 1
        return {
            "use_cases": dict(use_cases),
            "models": dict(models),
            "compute_families": dict(families),
            "serving_patterns": dict(serving),
            "note": "Distribution of routing decisions — not a performance comparison",
        }


def run_demo(pack_id: str, **kwargs: Any) -> DemoRun:
    return DemoRunner(mock=kwargs.pop("mock", None)).run(pack_id, **kwargs)
