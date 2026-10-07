"""OpenAI-compatible model endpoint adapter with live health + TTFT streaming."""

from __future__ import annotations

import json
import time
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx

from token_factory.adapters.types import EndpointHealth


def _normalize_base(url: str) -> str:
    u = url.rstrip("/")
    if not u.startswith("http"):
        # host:port form
        if "://" not in u:
            u = f"http://{u}"
    return u


class OpenAIModelEndpointAdapter:
    implementation = "openai_compatible"
    mode = "live"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def health(self, *, base_url: str, model: str | None = None) -> EndpointHealth:
        base = _normalize_base(base_url)
        t0 = time.perf_counter()
        try:
            r = httpx.get(f"{base}/v1/models", timeout=min(self.timeout, 8.0))
            latency = int((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                return EndpointHealth(
                    reachable=False,
                    model_available=False,
                    latency_ms=latency,
                    detail=f"HTTP {r.status_code}",
                    model=model,
                )
            body = r.json()
            ids = {m.get("id") for m in (body.get("data") or []) if isinstance(m, dict)}
            available = True if model is None else (model in ids or any(model and model in (i or "") for i in ids))
            # Some AIM servers list one id — treat non-empty catalog as available when model matches served name loosely
            if model and not available and ids:
                available = any(model.split("/")[-1] in (i or "") for i in ids) or len(ids) == 1
            return EndpointHealth(
                reachable=True,
                model_available=bool(available),
                latency_ms=latency,
                detail="ok" if available else "model not listed",
                model=model,
            )
        except Exception as exc:
            return EndpointHealth(
                reachable=False,
                model_available=False,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                detail=str(exc)[:200],
                model=model,
            )

    def complete(
        self, *, base_url: str, model: str, prompt: str, **kwargs: Any
    ) -> dict[str, Any]:
        base = _normalize_base(base_url)
        t0 = time.perf_counter()
        r = httpx.post(
            f"{base}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": int(kwargs.get("max_tokens") or 64),
                "stream": False,
            },
            timeout=float(kwargs.get("timeout") or 120.0),
        )
        if r.status_code >= 400:
            raise RuntimeError(f"endpoint HTTP {r.status_code}: {r.text[:400]}")
        body = r.json()
        body["_duration_ms"] = int((time.perf_counter() - t0) * 1000)
        body["mock"] = False
        body["_endpoint"] = base
        return body

    def stream(
        self, *, base_url: str, model: str, prompt: str, **kwargs: Any
    ) -> Iterator[dict[str, Any]]:
        """Yield parsed SSE chunks; first content chunk enables genuine TTFT."""
        base = _normalize_base(base_url)
        with httpx.stream(
            "POST",
            f"{base}/v1/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": int(kwargs.get("max_tokens") or 128),
                "stream": True,
            },
            timeout=float(kwargs.get("timeout") or 180.0),
        ) as resp:
            if resp.status_code >= 400:
                raise RuntimeError(f"stream HTTP {resp.status_code}: {resp.read()[:400]!r}")
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue


def parse_host_port(endpoint: str) -> tuple[str, int]:
    """Parse host/port from URL or host:port for legacy endpoints.yaml."""
    ep = endpoint.strip()
    if "://" not in ep:
        if ":" in ep:
            host, _, port_s = ep.rpartition(":")
            return host, int(port_s)
        return ep, 8000
    parsed = urlparse(ep if "://" in ep else f"http://{ep}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    return host, port
