"""Demo observability instrumentation — attributes + low-cardinality counters.

Latency/TTFT may be recorded as telemetry only. Never aggregate into
comparative hardware performance claims.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DemoSpan:
    """In-memory span / event record for a single demo request."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def add_event(self, name: str, **attrs: Any) -> None:
        self.events.append({"name": name, **attrs})


class DemoInstrumentor:
    """Process-local instrumentation sink used by the demo runner.

    Prometheus-style counters use low-cardinality labels only:
    scenario / use_case / compute_family / model / validation_status.
    Request UUIDs are stored on spans/logs, never as counter labels.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.spans: list[DemoSpan] = []
        self.counters: dict[str, dict[tuple[tuple[str, str], ...], int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.last_attributes: dict[str, Any] = {}

    def start_span(self, name: str, **attributes: Any) -> DemoSpan:
        span = DemoSpan(name=name, attributes=dict(attributes))
        with self._lock:
            self.spans.append(span)
            self.last_attributes = dict(attributes)
        return span

    def emit_request(
        self,
        *,
        demo_run_id: str,
        scenario_id: str,
        request_id: str,
        use_case: str | None,
        policy: str | None,
        serving_pattern: str | None,
        lifecycle: str | None,
        model: str | None,
        compute: str | None,
        compute_family: str | None,
        endpoint: str | None,
        fallback_used: bool,
        validation_status: str,
        duration_ms: float | None = None,
        ttft_ms: float | None = None,
        classify_ms: float | None = None,
    ) -> DemoSpan:
        attrs = {
            "demo_run_id": demo_run_id,
            "scenario_id": scenario_id,
            "request_id": request_id,
            "classified_use_case": use_case,
            "policy_profile": policy,
            "serving_pattern": serving_pattern,
            "lifecycle": lifecycle,
            "selected_model": model,
            "selected_compute": compute,
            "selected_compute_family": compute_family,
            "selected_endpoint": endpoint,
            "fallback_used": fallback_used,
            "validation_status": validation_status,
        }
        if duration_ms is not None:
            attrs["duration_ms"] = duration_ms
        if ttft_ms is not None:
            attrs["ttft_ms"] = ttft_ms
        if classify_ms is not None:
            attrs["classify_ms"] = classify_ms

        span = self.start_span("token_factory.demo.request", **attrs)

        labels = (
            ("scenario", scenario_id or "unknown"),
            ("use_case", (use_case or "unknown")[:64]),
            ("compute_family", compute_family or "unknown"),
            ("model", (model or "unknown")[:64]),
            ("validation_status", validation_status),
        )
        self.inc("token_factory_demo_requests_total", labels)
        self.inc(
            "token_factory_demo_validation_total",
            labels,
        )
        if fallback_used:
            self.inc(
                "token_factory_demo_fallback_total",
                (
                    ("scenario", scenario_id or "unknown"),
                    ("use_case", (use_case or "unknown")[:64]),
                    ("compute_family", compute_family or "unknown"),
                ),
            )
        self.inc(
            "token_factory_demo_route_total",
            (
                ("scenario", scenario_id or "unknown"),
                ("compute_family", compute_family or "unknown"),
                ("model", (model or "unknown")[:64]),
            ),
        )
        return span

    def inc(self, name: str, labels: tuple[tuple[str, str], ...], value: int = 1) -> None:
        with self._lock:
            self.counters[name][labels] += value

    def get_counter(self, name: str) -> dict[tuple[tuple[str, str], ...], int]:
        with self._lock:
            return dict(self.counters.get(name) or {})

    def prometheus_text(self) -> str:
        """Export counters in Prometheus exposition format (no request UUID labels)."""
        lines: list[str] = []
        with self._lock:
            for metric, series in sorted(self.counters.items()):
                lines.append(f"# TYPE {metric} counter")
                for labels, value in series.items():
                    label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                    lines.append(f"{metric}{{{label_str}}} {value}")
        return "\n".join(lines) + ("\n" if lines else "")

    def has_expected_attributes(self, request_id: str) -> bool:
        required = {
            "demo_run_id",
            "scenario_id",
            "request_id",
            "selected_model",
            "selected_compute",
            "lifecycle",
            "serving_pattern",
            "fallback_used",
        }
        for span in self.spans:
            if span.attributes.get("request_id") == request_id:
                return required.issubset(span.attributes.keys())
        return False

    def reset(self) -> None:
        with self._lock:
            self.spans.clear()
            self.counters.clear()
            self.last_attributes = {}


# Process-wide default instrumentor (tests may replace / reset)
INSTRUMENTOR = DemoInstrumentor()


def get_instrumentor() -> DemoInstrumentor:
    return INSTRUMENTOR
