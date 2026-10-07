"""Model router adapter wrapping vLLM Semantic Router (OSS default)."""

from __future__ import annotations

from typing import Any

from token_factory.adapters.types import RoutingDecision
from token_factory.demo.adapters import LiveClassifyAdapter, MockClassifyAdapter


def _body_to_routing(
    classify_body: dict[str, Any], *, objective: str | None = None
) -> RoutingDecision:
    classification = classify_body.get("classification") or {}
    intent = classification.get("category") or classify_body.get("category")
    conf = classification.get("confidence")
    route = None
    rd = classify_body.get("routing_decision")
    if isinstance(rd, dict):
        route = rd.get("route") or rd.get("name")
    elif isinstance(rd, str):
        route = rd
    return RoutingDecision(
        intent=str(intent) if intent else None,
        objective=objective,
        route=str(route) if route else None,
        confidence=float(conf) if conf is not None else None,
        mock=bool(classify_body.get("mock")),
    )


class VLLMSRModelRouterAdapter:
    implementation = "vllm_semantic_router"
    mode = "live"

    def __init__(self, base_url: str | None = None):
        self._live = LiveClassifyAdapter(base_url=base_url)

    def classify(self, text: str) -> dict[str, Any]:
        return self._live.classify(text)

    def to_routing_decision(
        self, classify_body: dict[str, Any], *, objective: str | None = None
    ) -> RoutingDecision:
        return _body_to_routing(classify_body, objective=objective)


class MockModelRouterAdapter:
    implementation = "mock"
    mode = "mock"

    def __init__(self, hint: str | None = None):
        self._mock = MockClassifyAdapter(hint=hint)

    def classify(self, text: str) -> dict[str, Any]:
        return self._mock.classify(text)

    def to_routing_decision(
        self, classify_body: dict[str, Any], *, objective: str | None = None
    ) -> RoutingDecision:
        return _body_to_routing(classify_body, objective=objective)
