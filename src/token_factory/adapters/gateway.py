"""AI Gateway adapter — Envoy AI Gateway OSS default."""

from __future__ import annotations

from typing import Any

import httpx

from token_factory.demo.adapters import LiveChatAdapter, MockChatAdapter


class EnvoyAIGatewayAdapter:
    implementation = "envoy_ai_gateway"
    mode = "live"

    def __init__(self, base_url: str | None = None):
        self._chat = LiveChatAdapter(gateway_url=base_url)
        self.base_url = self._chat.gateway_url

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url.rstrip('/')}/v1/models", timeout=2.0)
            return r.status_code < 500
        except Exception:
            return False

    def chat_completions(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._chat.complete(prompt, model=model, **kwargs)


class MockGatewayAdapter:
    implementation = "mock"
    mode = "mock"

    def __init__(self) -> None:
        self._chat = MockChatAdapter()

    def health(self) -> bool:
        return True

    def chat_completions(self, prompt: str, *, model: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return self._chat.complete(prompt, model=model or "mock", **kwargs)
