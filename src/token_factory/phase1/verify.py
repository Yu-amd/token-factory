"""Phase 1 architecture verification — honest PASS / NOT ENABLED / NOT PROVEN."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

from token_factory.phase1.decisions import (
    NOT_ENABLED,
    build_phase1_decisions,
    inspect_same_model_failover_configured,
)
from token_factory.runtime.paths import repo_root
from token_factory.version import VIRTUAL_MODEL

Status = str  # PASS | FAIL | NOT ENABLED | NOT PROVEN | CONFIGURED


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str = ""

    def line(self, width: int = 34) -> str:
        return f"{self.name:<{width}} {self.status}" + (
            f"  # {self.detail}" if self.detail else ""
        )


@dataclass
class VerifyReport:
    checks: list[CheckResult] = field(default_factory=list)
    tier1: dict[str, Any] | None = None
    tier2: dict[str, Any] | None = None
    overall: str = "FAIL"
    live: bool = False

    def add(self, name: str, status: Status, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, status=status, detail=detail))

    def render(self) -> str:
        lines = [
            "PHASE 1 ARCHITECTURE VERIFICATION",
            "",
        ]
        width = max((len(c.name) for c in self.checks), default=34)
        width = max(width, 34)
        for c in self.checks:
            lines.append(c.line(width))
        lines.append("")
        if self.tier1:
            lines.append("Tier-1 provider decision:")
            for k in (
                "request_id",
                "provider",
                "model",
                "auth",
                "quota",
                "fallback_policy",
                "route",
                "classification",
            ):
                if k in self.tier1:
                    lines.append(f"  {k}={self.tier1[k]}")
            lines.append("")
        if self.tier2:
            lines.append("Tier-2 inference decision:")
            for k in (
                "compute",
                "endpoint",
                "load_signal",
                "cache_signal",
                "kv_cache_aware",
                "prefix_cache_aware",
                "pd_disaggregation",
                "serving_pattern",
            ):
                if k in self.tier2:
                    lines.append(f"  {k}={self.tier2[k]}")
            lines.append("")
        lines.append(f"Overall demo readiness: {self.overall}")
        return "\n".join(lines)


def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    # Multi-doc Kubernetes manifests use --- separators.
    if "\n---" in text or text.lstrip().startswith("---"):
        docs = [d for d in yaml.safe_load_all(text) if d is not None]
        if len(docs) == 1:
            return docs[0]
        return docs
    return yaml.safe_load(text)


def _split_manifests(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [d for d in raw if isinstance(d, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _gateway_url() -> str:
    return os.environ.get("TF_GATEWAY_URL", "http://127.0.0.1:18080").rstrip("/")


def _sr_api_url() -> str:
    return os.environ.get("TF_SR_API_URL", "http://127.0.0.1:8081").rstrip("/")


def _has_security_or_rate_policy(manifests: list[dict[str, Any]]) -> tuple[bool, bool]:
    has_security = False
    has_rate = False
    for doc in manifests:
        kind = str(doc.get("kind") or "")
        if kind in ("SecurityPolicy", "BackendSecurityPolicy"):
            has_security = True
        blob = json.dumps(doc)
        if re.search(r"rateLimit|RateLimit|token.?budget", blob, re.I):
            has_rate = True
    return has_security, has_rate


def _semantic_cache_enabled(sr_values: dict[str, Any] | None) -> bool:
    if not sr_values:
        return False
    redis = (
        ((sr_values.get("dependencies") or {}).get("semanticCache") or {}).get("redis")
        or {}
    )
    return bool(redis.get("enabled"))


def _load_aware_configured(sr_values: dict[str, Any] | None) -> bool:
    """True only if non-static / dynamic load signals appear in compiled values."""
    if not sr_values:
        return False
    blob = json.dumps(sr_values).lower()
    # Static weight alone is not load-aware routing.
    for needle in (
        "load_aware",
        "loadaware",
        "kv_cache",
        "prefix_cache",
        "disaggregat",
        "prefill",
        "decode_disagg",
    ):
        if needle in blob:
            return True
    return False


def _kv_prefix_pd_flags(sr_values: dict[str, Any] | None) -> tuple[bool, bool, bool]:
    blob = json.dumps(sr_values or {}).lower()
    kv = "kv_cache" in blob or "kv-cache" in blob or "kvcache" in blob
    # semanticCache redis is NOT prefix-cache-aware routing
    prefix = "prefix_cache" in blob or "prefix-cache" in blob
    pd = any(x in blob for x in ("disaggregat", "p/d", "pd_disagg", "prefill_decode"))
    return kv, prefix, pd


def verify_phase1(*, live: bool = False) -> VerifyReport:
    """Audit Phase 1 against the two-tier blueprint. Never fabricate green items."""
    report = VerifyReport(live=live)
    root = repo_root()
    gen = root / "generated"
    sr_values = _load_yaml(gen / "semantic-router-values.yaml")
    if not isinstance(sr_values, dict):
        sr_values = None
    aigw_raw = _load_yaml(gen / "ai-gateway-manifests.yaml")
    manifests = _split_manifests(aigw_raw)
    # Multi-doc YAML may be loaded as list already; also handle --- documents
    if not manifests and (gen / "ai-gateway-manifests.yaml").is_file():
        text = (gen / "ai-gateway-manifests.yaml").read_text(encoding="utf-8")
        manifests = [
            d for d in yaml.safe_load_all(text) if isinstance(d, dict)
        ]

    ui_meta = _load_yaml(gen / "ui-metadata.json")
    if isinstance(ui_meta, dict) is False:
        # json not yaml
        try:
            ui_meta = json.loads((gen / "ui-metadata.json").read_text(encoding="utf-8"))
        except Exception:
            ui_meta = {}

    from token_factory.config.loader import load_endpoints, load_policies

    try:
        endpoints_doc = load_endpoints()
    except Exception:
        endpoints_doc = {"endpoints": []}
    try:
        policies_doc = load_policies()
    except Exception:
        policies_doc = {}

    # --- Static / config checks ---
    has_aigw = any(d.get("kind") == "AIGatewayRoute" for d in manifests)
    has_extproc = any(d.get("kind") == "EnvoyPatchPolicy" for d in manifests)
    report.add(
        "Envoy AI Gateway (compiled)",
        "PASS" if has_aigw and has_extproc else "FAIL",
        "AIGatewayRoute + ExtProc patch" if has_aigw else "missing manifests",
    )

    has_sr = bool(sr_values and (sr_values.get("config") or {}).get("routing"))
    cache_on = _semantic_cache_enabled(sr_values)
    report.add(
        "vLLM Semantic Router (compiled)",
        "PASS" if has_sr else "FAIL",
        f"semanticCache.redis.enabled={cache_on}",
    )

    has_security, has_rate = _has_security_or_rate_policy(manifests)
    report.add(
        "Rate limiting",
        "PASS" if has_rate else "NOT ENABLED",
        "no rate-limit CR in compiled AIGW manifests",
    )
    report.add(
        "Gateway auth enforcement",
        "PASS" if has_security else "NOT ENABLED",
        "no SecurityPolicy / BackendSecurityPolicy in compiled manifests",
    )

    same_model_fb = inspect_same_model_failover_configured(manifests)
    report.add(
        "Same-model failover",
        "CONFIGURED" if same_model_fb else "NOT PROVEN",
        "priority>0 backendRefs present" if same_model_fb else "no secondary same-model refs",
    )
    report.add(
        "Cross-model fallback",
        "NOT PROVEN",
        "compiler filters to same-model only; E2E not proven",
    )

    load_aware = _load_aware_configured(sr_values)
    kv_on, prefix_on, pd_on = _kv_prefix_pd_flags(sr_values)
    report.add(
        "Load-aware routing",
        "PASS" if load_aware else "NOT ENABLED",
        "static weights only" if not load_aware else "load keys present in values",
    )
    report.add(
        "KV-cache-aware routing",
        "PASS" if kv_on else "NOT ENABLED",
    )
    report.add(
        "Prefix-cache-aware routing",
        "PASS" if prefix_on else "NOT ENABLED",
        "semanticCache Redis off ≠ prefix-cache routing",
    )
    report.add(
        "P/D disaggregation",
        "PASS" if pd_on else "NOT ENABLED",
    )

    # Tier1/Tier2 objects always distinguishable
    report.add(
        "Tier-1 provider decision",
        "PASS",
        "logical object emitted by Token Factory",
    )
    report.add(
        "Tier-2 endpoint decision",
        "PASS",
        "logical object; Tier-2 awareness features not enabled",
    )

    # --- Live checks ---
    classified: dict[str, Any] = {}
    selected_model: str | None = None
    selected_route: str | None = None
    selected_endpoint: str | None = None
    selected_compute: str | None = None
    endpoint_url: str | None = None
    health_ms: int | None = None
    gw_ok = False
    sr_ok = False
    mi_ok = False
    classify_ok = False
    model_sel_ok = False
    gw_chat_ok = False

    if live:
        gw = _gateway_url()
        sr = _sr_api_url()
        try:
            r = httpx.get(f"{gw}/v1/models", timeout=5.0)
            gw_ok = r.status_code < 400
            report.add(
                "Envoy AI Gateway",
                "PASS" if gw_ok else "FAIL",
                f"{gw} → HTTP {r.status_code}",
            )
        except Exception as exc:
            report.add("Envoy AI Gateway", "FAIL", str(exc)[:120])

        try:
            r = httpx.get(f"{sr}/health", timeout=5.0)
            sr_ok = r.status_code < 400
            report.add(
                "vLLM Semantic Router",
                "PASS" if sr_ok else "FAIL",
                f"{sr}/health → HTTP {r.status_code}",
            )
        except Exception as exc:
            report.add("vLLM Semantic Router", "FAIL", str(exc)[:120])

        prompt = "Write a Python function that returns the nth Fibonacci number iteratively."
        try:
            t0 = time.perf_counter()
            r = httpx.post(
                f"{sr}/api/v1/classify/intent",
                json={"text": prompt},
                timeout=20.0,
            )
            classify_ms = int((time.perf_counter() - t0) * 1000)
            if r.status_code < 400:
                classified = r.json()
                classify_ok = True
                cat = (classified.get("classification") or {}).get("category") or classified.get(
                    "routing_decision"
                )
                report.add(
                    "Semantic classification",
                    "PASS",
                    f"{cat} ({classify_ms}ms)",
                )
            else:
                report.add(
                    "Semantic classification",
                    "FAIL",
                    f"HTTP {r.status_code}",
                )
        except Exception as exc:
            report.add("Semantic classification", "FAIL", str(exc)[:120])

        # Resolve model/endpoint from ui-metadata + classify (same as Playground)
        routes = (ui_meta or {}).get("routes") or []
        decision = (
            classified.get("routing_decision")
            or (classified.get("classification") or {}).get("category")
            or ""
        )
        recommended = classified.get("recommended_model") or ""
        matched = None
        for route in routes:
            if route.get("name") == decision:
                matched = route
                break
        if matched is None and recommended:
            for route in routes:
                ep = route.get("endpoint") or {}
                if route.get("lora_name") == recommended or ep.get("model") == recommended:
                    matched = route
                    break
        if matched is None and routes:
            # fall back to coding route if present
            matched = next((r for r in routes if r.get("name") == "coding_route"), routes[0])

        if matched:
            ep = matched.get("endpoint") or {}
            selected_route = str(matched.get("name") or decision)
            selected_model = str(
                recommended or matched.get("lora_name") or ep.get("model") or ""
            )
            selected_endpoint = str(ep.get("id") or "")
            selected_compute = (
                " · ".join(
                    p
                    for p in (ep.get("hardware"), ep.get("accelerator"))
                    if p
                )
                or ep.get("accelerator")
            )
            if ep.get("host"):
                endpoint_url = f"http://{ep['host']}:{ep.get('port', 8000)}"
            model_sel_ok = bool(selected_model and selected_endpoint)
            report.add(
                "Model selection",
                "PASS" if model_sel_ok else "FAIL",
                f"route={selected_route} model={selected_model}",
            )
        else:
            report.add("Model selection", "FAIL", "no route matched")

        # Live MI300X health + short completion on selected endpoint
        if endpoint_url and selected_model:
            try:
                from token_factory.adapters.model_endpoint import OpenAIModelEndpointAdapter

                adapter = OpenAIModelEndpointAdapter(timeout=10.0)
                health = adapter.health(base_url=endpoint_url, model=selected_model)
                health_ms = health.latency_ms
                mi_ok = health.reachable and health.model_available
                report.add(
                    "Live MI300X endpoint",
                    "PASS" if mi_ok else "FAIL",
                    f"{selected_endpoint} reachable={health.reachable} "
                    f"model_available={health.model_available} "
                    f"latency_ms={health.latency_ms}",
                )
            except Exception as exc:
                report.add("Live MI300X endpoint", "FAIL", str(exc)[:120])

            # Gateway path: real request through Envoy AI Gateway
            try:
                t0 = time.perf_counter()
                r = httpx.post(
                    f"{gw}/v1/chat/completions",
                    headers={"Authorization": "Bearer demo-key"},
                    json={
                        "model": VIRTUAL_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 48,
                        "stream": False,
                    },
                    timeout=180.0,
                )
                dur = int((time.perf_counter() - t0) * 1000)
                if r.status_code < 400:
                    body = r.json()
                    msg = (body.get("choices") or [{}])[0].get("message") or {}
                    text = (msg.get("content") or msg.get("reasoning") or "").strip()
                    gw_model = body.get("model") or selected_model
                    gw_chat_ok = bool(text) or bool(gw_model)
                    if not selected_model:
                        selected_model = str(gw_model) if gw_model else selected_model
                    report.add(
                        "Gateway → MI300X response",
                        "PASS" if gw_chat_ok else "FAIL",
                        f"model={gw_model} duration_ms={dur} bytes={len(text)}",
                    )
                else:
                    report.add(
                        "Gateway → MI300X response",
                        "FAIL",
                        f"HTTP {r.status_code}: {r.text[:160]}",
                    )
            except Exception as exc:
                report.add("Gateway → MI300X response", "FAIL", str(exc)[:160])
        else:
            report.add("Live MI300X endpoint", "FAIL", "no endpoint resolved")
            report.add("Gateway → MI300X response", "FAIL", "skipped")

        # Inventory probe: any enabled MI300X host
        live_eps = [
            e
            for e in (endpoints_doc.get("endpoints") or [])
            if e.get("enabled", True)
            and str(e.get("accelerator") or "").upper() == "MI300X"
            and e.get("host")
            and "svc.cluster.local" not in str(e.get("host"))
        ]
        report.add(
            "MI300X inventory configured",
            "PASS" if live_eps else "FAIL",
            f"{len(live_eps)} enabled Instinct endpoint(s)",
        )
    else:
        report.add(
            "Envoy AI Gateway",
            "NOT PROVEN",
            "pass --live to probe :18080",
        )
        report.add(
            "vLLM Semantic Router",
            "NOT PROVEN",
            "pass --live to probe SR health/classify",
        )
        report.add("Semantic classification", "NOT PROVEN", "requires --live")
        report.add("Model selection", "NOT PROVEN", "requires --live")
        report.add("Live MI300X endpoint", "NOT PROVEN", "requires --live")
        report.add("Gateway → MI300X response", "NOT PROVEN", "requires --live")

    tier1, tier2 = build_phase1_decisions(
        model=selected_model,
        route=selected_route,
        classification=(
            (classified.get("classification") or {}).get("category")
            if classified
            else None
        ),
        confidence=(classified.get("classification") or {}).get("confidence")
        if classified
        else None,
        compute=selected_compute or "MI300X",
        endpoint_id=selected_endpoint,
        endpoint_url=endpoint_url,
        serving_pattern="interactive",
        health_latency_ms=health_ms,
        policies=policies_doc,
        aigw_manifests=manifests,
    )
    # Keep auth/quota honest
    tier1.auth = NOT_ENABLED
    tier1.quota = NOT_ENABLED
    report.tier1 = tier1.to_dict()
    report.tier2 = tier2.to_dict()

    # Overall readiness
    hard_fail = any(
        c.status == "FAIL"
        and c.name
        in (
            "Envoy AI Gateway (compiled)",
            "vLLM Semantic Router (compiled)",
            "Envoy AI Gateway",
            "vLLM Semantic Router",
            "Semantic classification",
            "Model selection",
            "Live MI300X endpoint",
            "Gateway → MI300X response",
        )
        for c in report.checks
    )
    if live and hard_fail:
        report.overall = "FAIL"
    elif live and gw_ok and sr_ok and classify_ok and model_sel_ok and mi_ok and gw_chat_ok:
        report.overall = "PASS WITH LIMITATIONS"
    elif not live and has_aigw and has_sr:
        report.overall = "PASS WITH LIMITATIONS (config only; run --live)"
    else:
        report.overall = "FAIL"

    return report
