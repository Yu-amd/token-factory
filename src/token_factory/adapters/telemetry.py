"""Telemetry adapter — extends existing demo Prometheus counters."""

from __future__ import annotations

from typing import Any

from token_factory.demo.observability import DemoInstrumentor


class PrometheusTelemetryAdapter:
    implementation = "prometheus_file"
    mode = "live"

    def __init__(self, instrumentor: DemoInstrumentor | None = None):
        self.instrumentor = instrumentor or DemoInstrumentor()

    def emit(self, name: str, labels: dict[str, str], *, value: float = 1.0) -> None:
        del value
        label_tuple = tuple(sorted((str(k), str(v)) for k, v in labels.items()))
        self.instrumentor.inc(name, label_tuple)

    def emit_phase2(
        self,
        *,
        request_type: str,
        governance_allowed: bool,
        peer: str | None = None,
        implementation: str = "mock",
    ) -> None:
        self.emit(
            "token_factory_agent_gateway_requests_total",
            {
                "request_type": request_type,
                "allowed": "true" if governance_allowed else "false",
                "implementation": implementation,
            },
        )
        self.emit(
            "token_factory_governance_decisions_total",
            {
                "decision": "allow" if governance_allowed else "deny",
                "implementation": implementation,
            },
        )
        self.emit("token_factory_request_type_total", {"request_type": request_type})
        if request_type == "mcp":
            self.emit("token_factory_mcp_requests_total", {"peer": peer or "demo-mcp"})
        elif request_type == "a2a":
            self.emit("token_factory_a2a_requests_total", {"peer": peer or "demo-subagent"})
        elif request_type == "model":
            self.emit("token_factory_model_route_total", {"peer": peer or "mi300x"})
