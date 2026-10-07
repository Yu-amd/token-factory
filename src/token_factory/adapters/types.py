"""Shared types for adapter contracts (no vendor lock-in)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RequestType = Literal["model", "mcp", "a2a"]
AdapterMode = Literal["live", "mock", "disabled"]


@dataclass
class RequestContext:
    request_id: str
    principal: str = "engineering.user"
    business_unit: str = "Engineering"
    policy_pack: str = "amd-balanced"
    request_type: RequestType = "model"
    intent: str | None = None
    data_classification: str = "internal"
    lifecycle: str = "production"
    objective: str = "balanced"
    prompt: str = ""
    tool_name: str | None = None
    agent_task: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "principal": self.principal,
            "business_unit": self.business_unit,
            "policy_pack": self.policy_pack,
            "request_type": self.request_type,
            "intent": self.intent,
            "data_classification": self.data_classification,
            "lifecycle": self.lifecycle,
            "objective": self.objective,
            "prompt": self.prompt,
            "tool_name": self.tool_name,
            "agent_task": self.agent_task,
            "extras": self.extras,
        }


@dataclass
class GovernanceDecision:
    allowed: bool
    authn: str = "PASS"
    authz: str = "PASS"
    mcp_policy: str = "N/A"
    a2a_policy: str = "N/A"
    quota: str = "PASS"
    reason: str = ""
    implementation: str = "mock"
    mode: AdapterMode = "mock"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "authn": self.authn,
            "authz": self.authz,
            "mcp_policy": self.mcp_policy,
            "a2a_policy": self.a2a_policy,
            "quota": self.quota,
            "reason": self.reason,
            "implementation": self.implementation,
            "mode": self.mode,
        }


@dataclass
class RoutingDecision:
    intent: str | None = None
    objective: str | None = None
    model: str | None = None
    compute: str | None = None
    endpoint_id: str | None = None
    route: str | None = None
    confidence: float | None = None
    mock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "objective": self.objective,
            "model": self.model,
            "compute": self.compute,
            "endpoint_id": self.endpoint_id,
            "route": self.route,
            "confidence": self.confidence,
            "mock": self.mock,
        }


@dataclass
class EndpointHealth:
    reachable: bool
    model_available: bool
    latency_ms: int | None = None
    detail: str = ""
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reachable": self.reachable,
            "model_available": self.model_available,
            "latency_ms": self.latency_ms,
            "detail": self.detail,
            "model": self.model,
        }


@dataclass
class PeerResult:
    ok: bool
    peer: str
    request_type: RequestType
    content: str
    latency_ms: int | None = None
    mock: bool = True
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "peer": self.peer,
            "request_type": self.request_type,
            "content": self.content,
            "latency_ms": self.latency_ms,
            "mock": self.mock,
            "extras": self.extras,
        }
