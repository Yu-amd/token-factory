"""Honest Tier 1 / Tier 2 decision objects for Phase 1.

Tier 1 / Tier 2 are logical labels over a single Envoy + vLLM-SR path.
Capabilities that are not configured and exercised are marked ``not enabled``
— never fabricated as active load/cache/P-D decisions.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


NOT_ENABLED = "not enabled"


@dataclass
class Tier1ProviderDecision:
    """Provider / model decision (logical Tier 1 — Provider Gateway)."""

    request_id: str
    provider: str = "on-prem-amd"
    model: str | None = None
    auth: str = NOT_ENABLED
    quota: str = NOT_ENABLED
    fallback_policy: str = NOT_ENABLED
    route: str | None = None
    classification: str | None = None
    confidence: float | None = None
    notes: str = (
        "Logical Tier 1 over Envoy AI Gateway + vLLM-SR model selection; "
        "not a separate Provider Gateway runtime."
    )
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Tier2InferenceDecision:
    """Inference-placement decision (logical Tier 2 — Inference Gateway)."""

    compute: str | None = None
    endpoint: str | None = None
    endpoint_url: str | None = None
    load_signal: str = NOT_ENABLED
    cache_signal: str = NOT_ENABLED
    kv_cache_aware: str = NOT_ENABLED
    prefix_cache_aware: str = NOT_ENABLED
    pd_disaggregation: str = NOT_ENABLED
    serving_pattern: str | None = None
    health_latency_ms: int | None = None
    notes: str = (
        "Logical Tier 2 is endpoint placement from compile-time route→endpoint map. "
        "Load/KV/prefix/P-D awareness are not enabled in Token Factory config."
    )
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _fallback_policy_summary(
    policies: dict[str, Any] | None,
    *,
    same_model_secondary: bool = False,
) -> str:
    pol = (policies or {}).get("policy") or {}
    fb = pol.get("fallback") or {}
    if not fb.get("enabled", True):
        return "disabled in policy"
    chain = fb.get("chain") or []
    if not chain:
        return "enabled but empty chain"
    # Cross-model chain entries do not become AIGW secondary refs.
    if same_model_secondary:
        return (
            f"same-model secondary backendRefs configured; "
            f"policy chain={','.join(str(x) for x in chain)}; "
            f"cross-model failover NOT PROVEN"
        )
    return (
        f"policy chain={','.join(str(x) for x in chain)}; "
        f"AIGW emits same-model priority refs only — cross-model NOT PROVEN"
    )


def inspect_same_model_failover_configured(
    aigw_manifests: list[dict[str, Any]] | None = None,
) -> bool:
    """True if any AIGatewayRoute rule has a backendRef with priority > 0."""
    if not aigw_manifests:
        return False
    for doc in aigw_manifests:
        if doc.get("kind") != "AIGatewayRoute":
            continue
        for rule in (doc.get("spec") or {}).get("rules") or []:
            for ref in rule.get("backendRefs") or []:
                if int(ref.get("priority") or 0) > 0:
                    return True
    return False


def build_phase1_decisions(
    *,
    request_id: str | None = None,
    model: str | None = None,
    route: str | None = None,
    classification: str | None = None,
    confidence: float | None = None,
    compute: str | None = None,
    endpoint_id: str | None = None,
    endpoint_url: str | None = None,
    serving_pattern: str | None = None,
    health_latency_ms: int | None = None,
    policies: dict[str, Any] | None = None,
    aigw_manifests: list[dict[str, Any]] | None = None,
    provider: str = "on-prem-amd",
) -> tuple[Tier1ProviderDecision, Tier2InferenceDecision]:
    """Build Tier1/Tier2 objects from a real classify→route result.

    Auth/quota/cache/load/PD fields stay ``not enabled`` unless Token Factory
    both configures and exercises them (Friday: they are not).
    """
    rid = request_id or str(uuid.uuid4())
    same_model = inspect_same_model_failover_configured(aigw_manifests)

    load_signal = NOT_ENABLED
    if health_latency_ms is not None:
        # Probe latency is observational only — not used for routing selection.
        load_signal = (
            f"health_latency_ms={health_latency_ms} "
            f"(probe only; not used for routing)"
        )

    tier1 = Tier1ProviderDecision(
        request_id=rid,
        provider=provider,
        model=model,
        auth=NOT_ENABLED,
        quota=NOT_ENABLED,
        fallback_policy=_fallback_policy_summary(
            policies, same_model_secondary=same_model
        ),
        route=route,
        classification=classification,
        confidence=confidence,
    )
    tier2 = Tier2InferenceDecision(
        compute=compute,
        endpoint=endpoint_id,
        endpoint_url=endpoint_url,
        load_signal=load_signal,
        cache_signal=NOT_ENABLED,
        kv_cache_aware=NOT_ENABLED,
        prefix_cache_aware=NOT_ENABLED,
        pd_disaggregation=NOT_ENABLED,
        serving_pattern=serving_pattern,
        health_latency_ms=health_latency_ms,
    )
    return tier1, tier2
