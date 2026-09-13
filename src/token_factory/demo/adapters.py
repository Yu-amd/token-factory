"""Classification / chat adapters — live when services up, mock for CI."""

from __future__ import annotations

import os
import time
from typing import Any, Protocol

import httpx

from token_factory.demo.normalize import equivalence_set, normalize_label


class ClassifyAdapter(Protocol):
    def classify(self, prompt: str) -> dict[str, Any]:
        ...


class ChatAdapter(Protocol):
    def complete(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        ...


class MockClassifyAdapter:
    """Deterministic classifier using use_case_hint / keyword heuristics (no cluster)."""

    def __init__(self, hint: str | None = None):
        self.hint = hint

    def classify(self, prompt: str, *, use_case_hint: str | None = None) -> dict[str, Any]:
        hint = use_case_hint or self.hint
        category = _heuristic_category(prompt, hint)
        return {
            "classification": {"category": category, "confidence": 0.91},
            "routing_decision": _route_for_category(category),
            "recommended_model": None,
            "mock": True,
        }


class LiveClassifyAdapter:
    """POST Semantic Router /api/v1/classify/intent."""

    def __init__(self, base_url: str | None = None, timeout: float = 15.0):
        self.base_url = (
            base_url
            or os.environ.get("TF_SR_API_URL")
            or os.environ.get("TF_SR_URL")
            or "http://127.0.0.1:8081"
        )
        self.timeout = timeout

    def classify(self, prompt: str, *, use_case_hint: str | None = None) -> dict[str, Any]:
        del use_case_hint  # live path ignores hint
        t0 = time.perf_counter()
        r = httpx.post(
            f"{self.base_url.rstrip('/')}/api/v1/classify/intent",
            json={"text": prompt},
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"classify HTTP {r.status_code}: {r.text[:300]}")
        body = r.json()
        body["_classify_ms"] = int((time.perf_counter() - t0) * 1000)
        body["mock"] = False
        return body


class MockChatAdapter:
    """No-op completion for CI — records that a route was 'served'."""

    def complete(self, prompt: str, model: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "id": "mock-chat",
            "model": model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": f"[mock] acknowledged ({len(prompt)} chars)",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": max(1, len(prompt) // 4), "completion_tokens": 8},
            "mock": True,
        }


class LiveChatAdapter:
    def __init__(self, gateway_url: str | None = None, timeout: float = 120.0):
        self.gateway_url = gateway_url or os.environ.get(
            "TF_GATEWAY_URL", "http://127.0.0.1:18080"
        )
        self.timeout = timeout
        self.virtual_model = os.environ.get("TF_VIRTUAL_MODEL", "token-factory/auto")

    def complete(self, prompt: str, model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        r = httpx.post(
            f"{self.gateway_url.rstrip('/')}/v1/chat/completions",
            headers={"Authorization": "Bearer demo-key"},
            json={
                "model": model or self.virtual_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": int(kwargs.get("max_tokens") or 64),
                "stream": False,
            },
            timeout=self.timeout,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"gateway HTTP {r.status_code}: {r.text[:400]}")
        body = r.json()
        body["_duration_ms"] = int((time.perf_counter() - t0) * 1000)
        body["mock"] = False
        return body


def resolve_adapters(
    *,
    mock: bool | None = None,
    use_case_hint: str | None = None,
) -> tuple[Any, Any]:
    """Pick live adapters when services respond; otherwise mock.

    ``mock=True`` forces mocks. ``mock=False`` forces live (may raise).
    ``mock=None`` auto-detects.
    """
    if mock is True:
        return MockClassifyAdapter(hint=use_case_hint), MockChatAdapter()
    if mock is False:
        return LiveClassifyAdapter(), LiveChatAdapter()

    # Auto: probe SR health
    sr = (
        os.environ.get("TF_SR_API_URL")
        or os.environ.get("TF_SR_URL")
        or "http://127.0.0.1:8081"
    )
    try:
        r = httpx.get(f"{sr.rstrip('/')}/health", timeout=1.5)
        if r.status_code < 400:
            return LiveClassifyAdapter(sr), LiveChatAdapter()
    except Exception:
        pass
    return MockClassifyAdapter(hint=use_case_hint), MockChatAdapter()


def _heuristic_category(prompt: str, hint: str | None) -> str:
    if hint:
        # Map use-case hint to an SR-like domain label
        h = normalize_label(hint)
        if h in equivalence_set("coding-assistant") or "coding" in h or "code" in h:
            return "computer science"
        if h in equivalence_set("complex-reasoning") or "reason" in h or "math" in h:
            return "math"
        if h in equivalence_set("vlm") or "vision" in h or "multimodal" in h:
            return "other"  # SR may not have vision domain; soft-match via hint
        if h in equivalence_set("batch-summarization") or "summar" in h:
            return "business"
        if h in equivalence_set("enterprise-chat") or "chat" in h:
            return "business"
        # Prefer returning the use-case id itself for soft match
        return hint

    lower = prompt.lower()
    coding_kw = ("python", "function", "code", "implement", "lru", "compile", "debug", "refactor")
    reason_kw = ("prove", "reason", "theorem", "derive", "logic", "step by step")
    vision_kw = ("image", "diagram", "screenshot", "photo", "vlm", "multimodal", "vision")
    batch_kw = ("summarize", "batch", "extract all", "classify these", "documents")
    if any(k in lower for k in coding_kw):
        return "computer science"
    if any(k in lower for k in reason_kw):
        return "math"
    if any(k in lower for k in vision_kw):
        return "other"
    if any(k in lower for k in batch_kw):
        return "business"
    return "other"


def _route_for_category(category: str) -> str:
    c = normalize_label(category)
    if c in ("computer science", "computerscience") or "coding" in c:
        return "coding_route"
    if c in ("math", "physics", "chemistry", "engineering"):
        return "reasoning_route"
    return "general_route"
