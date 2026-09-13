"""Deterministic AMD Opinionated Routing recommendation engine.

Separates:
  AIM support (can run) — catalog/aims.yaml (+ tech-preview merge for MI350P)
  Recommendation (should run) — scoring + overrides + lifecycle filter
  Runtime availability — endpoint inventory overlay

Lifecycle (ga|preview|tech-preview|planned) is orthogonal to support_level
(optimized|preview|unoptimized|general). Tech Preview is never silent GA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from token_factory.catalog.eligibility import SUPPORT_RANK
from token_factory.routing_matrix.evidence import (
    audit_evidence_gaps,
    cap_is_false,
    cap_is_true,
    cap_is_unknown,
    cap_truth,
    evidence_badge,
    evidence_category_for_model,
    evidence_confidence_score,
    load_evidence_catalog,
    maturity_for_model,
    normalize_override,
    performance_evidence_status,
    quality_fit_from_strengths,
    recommendation_confidence,
    records_for_model,
    review_status_for_model,
    strength_level,
)
from token_factory.routing_matrix.loader import load_routing_bundle
from token_factory.routing_matrix.portfolio import (
    EXECUTIVE_TOP_ROWS,
    capability_cell_from_aim,
    catalog_counts as build_catalog_counts,
    catalog_model_ids,
    classify_row_status,
    compute_counts as build_compute_counts,
    executive_display_rows,
    filter_columns,
    filter_display_rows,
    metadata_incomplete,
    order_portfolio_rows,
    unsupported_cell,
    why_not_recommended,
)

LEVEL_ORDER = {
    "PREFERRED": 5,
    "RECOMMENDED": 4,
    "ACCEPTABLE": 3,
    "SUPPORTED": 2,
    "NOT_SUPPORTED": 1,
}

CAP_KEY = {
    "text-generation": "text_generation",
    "text_generation": "text_generation",
    "coding": "coding",
    "reasoning": "reasoning",
    "vision": "vision",
    "multimodal": "multimodal",
    "tool-use": "tool_use",
    "tool_use": "tool_use",
    "long-context": "long_context",
    "long_context": "long_context",
    "agentic-coding": "agentic_coding",
    "agentic_coding": "agentic_coding",
    "repository-reasoning": "repository_reasoning",
    "repository_reasoning": "repository_reasoning",
}

SIZE_TIER = {
    "small": 1,
    "medium": 2,
    "large": 3,
    "frontier": 4,
    "unknown": 2,
}

TIER_NAME = {"basic": 1, "standard": 2, "high": 3, "frontier": 4}

# Matrix focus columns for private-eval (Tech Preview / Preview) AIM cells.
# Always retained in UI columns; Executive view unions these into its truncated set.
PRIVATE_EVAL_COMPUTES = ("MI350P", "R9700", "W7900")
PRIVATE_EVAL_AVAILABILITY = "private-eval"
PRIVATE_EVAL_CHANNEL = "private-eval-container"
# Executive-only truncation budget (Portfolio never silently truncates).
MATRIX_TOP_ROWS = EXECUTIVE_TOP_ROWS

# Soft generation bias — tie-breaker only unless AMD_MEASURED evidence exists.
# Applied outside performance_fit (final sort nudge), not as a primary rank key.
INSTINCT_GEN_BIAS = {
    "MI250X": 0,
    "MI300X": 2,
    "MI325X": 1,
    "MI350P": 3,  # PCIe enterprise — not an alias of MI350X
    "MI350X": 4,
    "MI355X": 5,
}

OBJECTIVE_PREF_LABEL = {
    "quality": "PERFORMANCE_PREFERRED",
    "throughput": "PERFORMANCE_PREFERRED",
    "latency": "PERFORMANCE_PREFERRED",
    "token-cost": "ECONOMIC_PREFERRED",
    "lowest-cost-sufficient": "ECONOMIC_PREFERRED",
    "balanced": "BALANCED_PREFERRED",
    "edge-local": "EDGE_LOCAL_PREFERRED",
    "enterprise": "PRODUCTION_PREFERRED",
    "batch": "BATCH_PREFERRED",
    "local": "LOCAL_PREFERRED",
}

# Serving patterns (Interactive ≠ high traffic; Batch ≠ high-concurrency interactive)
SERVING_PATTERNS = (
    "interactive",
    "online-throughput",
    "batch",
    "offline-batch",
)

# Latency requirement levels derived from serving pattern + use-case overrides
LATENCY_LEVELS = ("critical", "important", "relaxed", "unconstrained")

SERVING_DEFAULT_LATENCY = {
    "interactive": "critical",
    "online-throughput": "important",
    "batch": "relaxed",
    "offline-batch": "unconstrained",
}

# Matrix UI: number only top N; full rank stays in cell detail
MATRIX_NUMBERED_TOP = 5

COST_EVIDENCE = ("MEASURED", "ESTIMATED", "RELATIVE", "UNKNOWN")

CIRCLED = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}


@dataclass
class Candidate:
    model: str
    compute_id: str
    family: str
    aim_support: str
    lifecycle: str
    recommendation: str
    rank: int | None = None
    score: float = 0.0
    confidence: str = "medium"
    reasons: list[str] = field(default_factory=list)
    cost_confidence: str = "relative"
    cost_evidence: str = "RELATIVE"
    relative_cost_class: str = "medium"
    hardware_cost_class: str = "medium"
    infrastructure_cost_class: str = "medium"
    token_economic_fit: float = 0.0
    endpoint_available: bool = False
    endpoint_id: str | None = None
    override: bool = False
    production_eligible: bool = True
    capability_fit: float = 0.0
    quality_fit: float = 0.0
    performance_fit: float = 0.0
    economic_fit: float = 0.0
    deployment_fit: float = 0.0
    lifecycle_fit: float = 0.0
    serving_pattern_fit: float = 0.0
    locality_fit: float = 0.0
    evidence_confidence: float = 0.0
    performance_evidence: dict[str, Any] = field(default_factory=dict)
    evidence_badge: str = "?"
    rationale: dict[str, list[str]] = field(default_factory=dict)
    policy_override: dict[str, Any] | None = None
    preference_label: str | None = None
    lifecycle_excluded: bool = False
    exclusion_reason: str | None = None
    exclusion_kind: str | None = None  # lifecycle | latency | serving_pattern | locality
    availability: str | None = None
    deployment_channel: str | None = None
    matrix_mark: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "compute": self.compute_id,
            "family": self.family,
            "aim_support": self.aim_support,
            "lifecycle": self.lifecycle,
            "recommendation": self.recommendation,
            "rank": self.rank,
            "score": round(self.score, 3),
            "confidence": self.confidence,
            "reasons": self.reasons,
            "cost_confidence": self.cost_confidence,
            "cost_evidence": self.cost_evidence,
            "relative_cost_class": self.relative_cost_class,
            "hardware_cost_class": self.hardware_cost_class,
            "infrastructure_cost_class": self.infrastructure_cost_class,
            "token_economic_fit": round(self.token_economic_fit, 3),
            "endpoint_available": self.endpoint_available,
            "endpoint_id": self.endpoint_id,
            "override": self.override,
            "production_eligible": self.production_eligible,
            "capability_fit": round(self.capability_fit, 3),
            "quality_fit": round(self.quality_fit, 3),
            "performance_fit": round(self.performance_fit, 3),
            "economic_fit": round(self.economic_fit, 3),
            "deployment_fit": round(self.deployment_fit, 3),
            "lifecycle_fit": round(self.lifecycle_fit, 3),
            "serving_pattern_fit": round(self.serving_pattern_fit, 3),
            "locality_fit": round(self.locality_fit, 3),
            "evidence_confidence": round(self.evidence_confidence, 3),
            "performance_evidence": self.performance_evidence,
            "evidence_badge": self.evidence_badge,
            "rationale": self.rationale,
            "policy_override": self.policy_override,
            "preference_label": self.preference_label,
            "lifecycle_excluded": self.lifecycle_excluded,
            "exclusion_reason": self.exclusion_reason,
            "exclusion_kind": self.exclusion_kind,
            "availability": self.availability,
            "deployment_channel": self.deployment_channel,
            "matrix_mark": self.matrix_mark,
            "why": self.reasons,
        }


class RecommendationEngine:
    def __init__(self, bundle: dict[str, Any] | None = None):
        self.bundle = bundle or load_routing_bundle()
        self.aims = {a["model"]: a for a in self.bundle["aims"].get("aims", [])}
        self.compute = {c["id"]: c for c in self.bundle["compute"].get("compute", [])}
        self.use_cases = {
            u["id"]: u for u in self.bundle["use_cases"].get("use_cases", [])
        }
        self.models = {m["model"]: m for m in self.bundle["models"].get("models", [])}
        self.cost = self.bundle["cost_model"]
        self.policy = self.bundle["policy"]
        self.objectives = {
            o["id"]: o for o in self.bundle["use_cases"].get("objectives", [])
        }
        self.aliases = self.bundle.get("aliases") or self.bundle["use_cases"].get(
            "priority_mode_aliases", {}
        )
        # Model aliases vs objective aliases — keep both
        self.model_aliases = self.bundle.get("aliases") or {}
        self.obj_aliases = self.bundle["use_cases"].get("priority_mode_aliases", {})
        self.lifecycle_modes = self.bundle["use_cases"].get("lifecycle_modes") or {}
        self.capability_floors = self.bundle["use_cases"].get("capability_floors") or {}
        self.evidence = self.bundle.get("evidence") or load_evidence_catalog()

    def list_use_cases(self) -> list[dict[str, Any]]:
        return [
            {
                "id": u["id"],
                "display_name": u.get("display_name", u["id"]),
                "category": u.get("category"),
            }
            for u in self.bundle["use_cases"].get("use_cases", [])
        ]

    def list_objectives(self) -> list[dict[str, Any]]:
        return list(self.bundle["use_cases"].get("objectives", []))

    def list_compute(self) -> list[dict[str, Any]]:
        return list(self.bundle["compute"].get("compute", []))

    def list_lifecycle_modes(self) -> list[dict[str, Any]]:
        out = []
        for mid, meta in self.lifecycle_modes.items():
            out.append(
                {
                    "id": mid,
                    "display_name": meta.get("display_name", mid),
                    "allow": list(meta.get("allow") or []),
                }
            )
        return out or [
            {"id": "production", "display_name": "Production", "allow": ["ga"]},
            {
                "id": "production-preview",
                "display_name": "Production + Preview",
                "allow": ["ga", "preview"],
            },
            {
                "id": "evaluation",
                "display_name": "Tech Preview / Evaluation",
                "allow": ["ga", "preview", "tech-preview"],
            },
            {
                "id": "all",
                "display_name": "All",
                "allow": ["ga", "preview", "tech-preview", "planned"],
            },
        ]

    def list_serving_patterns(self) -> list[dict[str, Any]]:
        labels = {
            "interactive": "Interactive",
            "online-throughput": "Online Throughput",
            "batch": "Batch",
            "offline-batch": "Offline Batch",
        }
        catalog = self.bundle["use_cases"].get("serving_patterns") or []
        if catalog:
            return list(catalog)
        return [{"id": sp, "display_name": labels[sp]} for sp in SERVING_PATTERNS]

    def resolve_serving_pattern(
        self, serving_pattern: str | None, use_case_id: str
    ) -> str:
        if serving_pattern:
            aliases = {
                "online": "online-throughput",
                "throughput": "online-throughput",
                "offline": "offline-batch",
                "offline_batch": "offline-batch",
                "online_throughput": "online-throughput",
            }
            sp = aliases.get(serving_pattern, serving_pattern)
            if sp in SERVING_PATTERNS:
                return sp
        uc = self.use_cases.get(use_case_id, {})
        preferred = uc.get("serving_patterns_preferred") or uc.get("serving_patterns") or []
        if preferred:
            return preferred[0]
        # Heuristic from workload concurrency / latency
        wl = uc.get("workload") or {}
        if wl.get("concurrency") == "low" and wl.get("latency_sensitivity") in (
            "low",
            "medium",
        ):
            return "batch"
        if wl.get("latency_sensitivity") in ("very-high", "high"):
            return "interactive"
        return "interactive"

    def resolve_latency_requirement(
        self,
        use_case_id: str,
        serving_pattern: str,
        latency_requirement: str | None = None,
    ) -> str:
        if latency_requirement in LATENCY_LEVELS:
            return latency_requirement  # type: ignore[return-value]
        uc = self.use_cases.get(use_case_id, {})
        explicit = uc.get("latency_requirement")
        if explicit in LATENCY_LEVELS:
            return explicit
        # Use-case overrides mapped from sensitivity
        sens = (uc.get("workload") or {}).get("latency_sensitivity")
        if sens == "very-high":
            return "critical"
        if sens == "high" and serving_pattern == "interactive":
            return "critical"
        if sens == "low":
            return "relaxed"
        return SERVING_DEFAULT_LATENCY.get(serving_pattern, "important")

    def _cost_evidence_for(self, compute_id: str) -> str:
        """MEASURED / ESTIMATED / RELATIVE / UNKNOWN — never fabricate numbers."""
        measured = (self.cost.get("measured") or {}).get("benchmarks") or []
        if any(b.get("compute") == compute_id for b in measured if isinstance(b, dict)):
            return "MEASURED"
        cc = (self.cost.get("compute_costs") or {}).get(compute_id) or {}
        if any(v is not None for v in cc.values() if not isinstance(v, dict)):
            return "ESTIMATED"
        compute = self.compute.get(compute_id, {})
        if compute.get("relative_cost_class") or compute.get("hardware_cost_class"):
            return "RELATIVE"
        return "UNKNOWN"

    def _matrix_mark_for(self, cand: Candidate) -> str:
        """User-facing matrix mark — number only top ~3–5; raw rank in detail."""
        if cand.lifecycle_excluded:
            return "⊘"
        rec = cand.recommendation
        rank = cand.rank
        if rec == "PREFERRED" and rank == 1:
            return "★"
        if rank is not None and 1 <= rank <= MATRIX_NUMBERED_TOP:
            if rank == 1 and rec in ("PREFERRED", "RECOMMENDED"):
                return "★"
            return CIRCLED.get(rank, str(rank))
        if rec == "PREFERRED":
            return "★"
        if rec == "RECOMMENDED":
            return "✓"
        if rec == "ACCEPTABLE":
            return "✓"
        if rec == "SUPPORTED":
            return "○"
        return "—"

    def resolve_objective(self, objective: str | None, use_case_id: str) -> str:
        if objective:
            return self.obj_aliases.get(objective, objective)
        uc = self.use_cases.get(use_case_id, {})
        return uc.get("optimization_default", "balanced")

    def resolve_lifecycle_mode(self, mode: str | None) -> str:
        if not mode:
            return "production"
        aliases = {
            "prod": "production",
            "ga": "production",
            "production+preview": "production-preview",
            "preview": "production-preview",
            "tech-preview": "evaluation",
            "eval": "evaluation",
            "evaluation": "evaluation",
            "tp": "evaluation",
            "all": "all",
        }
        return aliases.get(mode, mode)

    def _allowed_lifecycles(self, lifecycle_mode: str) -> set[str]:
        mode = self.resolve_lifecycle_mode(lifecycle_mode)
        meta = self.lifecycle_modes.get(mode) or {}
        allow = meta.get("allow")
        if allow:
            return set(allow)
        # Fallback defaults
        if mode == "production":
            return {"ga"}
        if mode == "production-preview":
            return {"ga", "preview"}
        if mode == "evaluation":
            return {"ga", "preview", "tech-preview"}
        return {"ga", "preview", "tech-preview", "planned"}

    def _model_caps(self, model: str) -> dict[str, Any]:
        meta = self.models.get(model, {})
        return meta.get("capabilities", {})

    def _model_tier(self, model: str) -> int:
        meta = self.models.get(model, {})
        explicit = meta.get("capability_tier")
        if explicit in TIER_NAME:
            return TIER_NAME[explicit]
        size = meta.get("size_class", "unknown")
        # Map size → qualitative tier (not ranking by parameter count)
        return {
            "small": 1,
            "medium": 2,
            "large": 3,
            "frontier": 4,
            "unknown": 2,
        }.get(size, 2)

    def _floor_tier(self, use_case_id: str) -> int:
        name = self.capability_floors.get(use_case_id, "standard")
        return TIER_NAME.get(name, 2)

    def _capability_ok(
        self, model: str, use_case: dict[str, Any], *, lifecycle_mode: str | None = None
    ) -> tuple[bool, str, str | None]:
        """Hard capability gate with tri-state handling.

        Returns (ok, why, exclusion_kind).
        unknown on a required capability → metadata-incomplete (not silent false).
        Production excludes unknown; evaluation/all may admit with degraded confidence.
        """
        caps = self._model_caps(model)
        required = (use_case.get("capabilities") or {}).get("required") or []
        mode = (lifecycle_mode or "production").lower()
        allow_unknown = mode in ("evaluation", "all", "tech-preview", "tech_preview")
        for req in required:
            key = CAP_KEY.get(req, req.replace("-", "_"))
            # multimodal requirement satisfied by vision
            if key == "multimodal" and (
                cap_is_true(caps.get("multimodal")) or cap_is_true(caps.get("vision"))
            ):
                continue
            # agentic_coding soft-satisfied by coding+tool_use when agentic unknown
            if key == "agentic_coding":
                val = caps.get(key, caps.get("coding"))
                if cap_is_true(val):
                    continue
                if cap_is_unknown(val) and allow_unknown:
                    continue
                if cap_is_unknown(val):
                    return (
                        False,
                        f"required capability '{req}' is unknown (metadata-incomplete)",
                        "metadata_incomplete",
                    )
                if not cap_is_true(val):
                    return False, f"missing required capability '{req}'", "capability"
                continue
            val = caps.get(key, False)
            if cap_is_true(val):
                continue
            if cap_is_unknown(val):
                if allow_unknown:
                    continue
                return (
                    False,
                    f"required capability '{req}' is unknown (metadata-incomplete)",
                    "metadata_incomplete",
                )
            return False, f"missing required capability '{req}'", "capability"
        return True, "ok", None

    def _aim_cells(self, model: str) -> list[tuple[str, str, str, str]]:
        """Return (family, compute_id, support_level, lifecycle)."""
        aim = self.aims.get(model)
        if not aim:
            return []
        out = []
        for family, mapping in (aim.get("support") or {}).items():
            if not isinstance(mapping, dict):
                continue
            for accel, cell in mapping.items():
                if isinstance(cell, dict):
                    support = str(cell.get("support") or "preview")
                    lifecycle = str(cell.get("lifecycle") or "ga")
                else:
                    support = str(cell)
                    lifecycle = "preview" if support == "preview" else "ga"
                out.append((family, accel, support, lifecycle))
        return out

    def _override_level(
        self, use_case_id: str, model: str, compute_id: str
    ) -> tuple[str | None, list[str], dict[str, Any] | None]:
        overrides = (self.policy.get("overrides") or {}).get(use_case_id) or {}
        model_ov = overrides.get(model) or {}
        cell = model_ov.get(compute_id)
        if not cell:
            return None, [], None
        norm = normalize_override(cell if isinstance(cell, dict) else {"recommendation": cell})
        decision = (norm or {}).get("decision")
        rationale = list((norm or {}).get("rationale") or [])
        return decision, rationale, norm

    def _base_level(self, aim_support: str, lifecycle: str) -> str:
        if lifecycle == "tech-preview":
            return "ACCEPTABLE"
        if aim_support == "optimized":
            return "RECOMMENDED"
        if aim_support == "preview":
            return "ACCEPTABLE"
        if aim_support == "general":
            return "ACCEPTABLE"
        return "SUPPORTED"

    def _hw_cost_rank(self, compute_id: str) -> int:
        compute = self.compute.get(compute_id, {})
        hw = compute.get("hardware_cost_class") or compute.get(
            "relative_cost_class", "medium"
        )
        return (self.cost.get("hardware_cost_rank") or self.cost.get("relative_cost_rank") or {}).get(
            hw, 3
        )

    def _rel_cost_rank(self, compute_id: str) -> int:
        compute = self.compute.get(compute_id, {})
        rel = compute.get("relative_cost_class", "medium")
        return (self.cost.get("relative_cost_rank") or {}).get(rel, 3)

    def _fits(
        self,
        *,
        use_case: dict[str, Any],
        use_case_id: str,
        objective: str,
        model: str,
        compute_id: str,
        family: str,
        aim_support: str,
        lifecycle: str,
        utilization: str,
        data_locality: bool,
        serving_pattern: str = "interactive",
        latency_requirement: str = "important",
    ) -> tuple[float, float, float, float, float, float, float, float, float, list[str]]:
        reasons: list[str] = []
        meta = self.models.get(model, {})
        compute = self.compute.get(compute_id, {})
        chars = compute.get("characteristics") or {}
        caps = self._model_caps(model)

        # --- capability_fit ---
        floor = self._floor_tier(use_case_id)
        tier = self._model_tier(model)
        if tier < floor:
            capability_fit = max(0.0, 0.35 * tier / floor)
            reasons.append(f"below capability floor ({tier}<{floor})")
        else:
            overshoot = tier - floor
            capability_fit = 1.0 - min(0.35, overshoot * 0.08)
            if overshoot == 0:
                reasons.append("meets capability floor exactly")
            else:
                reasons.append(f"clears capability floor (tier {tier}≥{floor})")

        pref_caps = (use_case.get("capabilities") or {}).get("preferred") or []
        for pref in pref_caps:
            key = CAP_KEY.get(pref, pref.replace("-", "_"))
            if cap_is_true(caps.get(key)):
                capability_fit = min(1.0, capability_fit + 0.05)
            elif cap_is_unknown(caps.get(key)):
                # unknown preferred caps degrade confidence later; tiny soft nudge only
                capability_fit = min(1.0, capability_fit + 0.01)

        # Specialization is a weak hint only (quality_fit carries task strengths)
        spec = meta.get("specialization")
        cat = use_case.get("category")
        if spec and cat and spec == cat:
            capability_fit = min(1.0, capability_fit + 0.03)
            reasons.append(f"weak specialization hint '{cat}'")

        # --- quality_fit (workload strengths; not model size) ---
        quality_fit, q_reasons = quality_fit_from_strengths(meta, use_case_id, use_case)
        reasons.extend(q_reasons)

        # --- performance_fit (runtime appropriateness; no generation auto-win) ---
        performance_fit = 0.45
        if chars.get("high_throughput"):
            performance_fit += 0.25
        if chars.get("high_concurrency") and utilization == "high":
            performance_fit += 0.2
            reasons.append("high concurrency × high-throughput compute")
        if chars.get("local_workstation") and utilization in ("low", "medium"):
            if serving_pattern == "interactive":
                performance_fit += 0.15
        if aim_support == "optimized":
            performance_fit += 0.1
        # INSTINCT_GEN_BIAS intentionally NOT applied here — tie-break in ranking only
        if family == "radeon" and utilization == "high":
            performance_fit -= 0.25
            reasons.append("high traffic: Radeon concurrency limited vs Instinct")
        # EPYC is NOT a GPU interactive competitor
        if family == "epyc" and serving_pattern == "interactive" and utilization == "high":
            performance_fit -= 0.30
            reasons.append("EPYC not suited to high-concurrency interactive serving")
        if family == "epyc" and serving_pattern in ("batch", "offline-batch"):
            performance_fit += 0.10
            reasons.append("EPYC fits batch / offline serving pattern")
        performance_fit = max(0.0, min(1.0, performance_fit))

        # --- economic_fit (token economic fit for workload; ≠ infrastructure cost class) ---
        hw_rank = self._hw_cost_rank(compute_id)
        economic_fit = (6 - hw_rank) / 5.0
        if utilization == "low" and (
            chars.get("cpu_inference")
            or chars.get("local_workstation")
            or chars.get("pcie_form_factor")
        ):
            economic_fit = min(1.0, economic_fit + 0.25)
            reasons.append("low traffic favors smaller footprint (EPYC/Radeon/PCIe)")
        if utilization == "high" and chars.get("high_throughput"):
            economic_fit = min(1.0, economic_fit + 0.3)
            reasons.append("high traffic: throughput class improves token economics")
        if utilization == "high" and family in ("radeon", "epyc"):
            economic_fit = max(0.0, economic_fit - 0.2)
        if utilization == "medium":
            if chars.get("high_throughput"):
                economic_fit = min(1.0, economic_fit + 0.08)
            if chars.get("cpu_inference") or chars.get("local_workstation"):
                economic_fit = min(1.0, economic_fit + 0.05)
        # Batch/offline: EPYC fleet utilization improves economic fit
        if serving_pattern in ("batch", "offline-batch") and chars.get("cpu_inference"):
            economic_fit = min(1.0, economic_fit + 0.2)
            reasons.append("batch/offline: CPU fleet utilization improves economic fit")
        economic_fit = max(0.0, min(1.0, economic_fit))

        # --- deployment_fit ---
        typical = (use_case.get("deployment") or {}).get("typical") or []
        dep = compute.get("deployment_class") or []
        deployment_fit = 0.45
        if typical and any(
            t in dep
            or (t == "enterprise" and ("datacenter" in dep or "enterprise-server" in dep))
            or (t in ("workstation", "local", "edge") and any(
                x in dep for x in ("workstation", "local", "edge", "departmental", "developer")
            ))
            for t in typical
        ):
            deployment_fit = 0.9
            reasons.append("deployment class matches use-case typical targets")
        elif typical:
            deployment_fit = 0.35

        # --- lifecycle_fit ---
        lifecycle_fit = {
            "ga": 1.0,
            "preview": 0.65,
            "tech-preview": 0.45,
            "planned": 0.2,
        }.get(lifecycle, 0.5)
        if lifecycle == "tech-preview":
            reasons.append("lifecycle=tech-preview (evaluation only; not production GA)")
        elif lifecycle == "preview":
            reasons.append("lifecycle=preview (Radeon/AIM preview; excluded from production)")

        # --- serving_pattern_fit ---
        serving_pattern_fit = 0.5
        if serving_pattern == "interactive":
            if chars.get("local_workstation") or chars.get("high_concurrency"):
                serving_pattern_fit = 0.85
            if family == "epyc":
                serving_pattern_fit = 0.25
                reasons.append("EPYC weak for interactive (CPU-centric, not GPU interactive)")
            if latency_requirement == "critical" and chars.get("high_concurrency"):
                serving_pattern_fit = min(1.0, serving_pattern_fit + 0.1)
        elif serving_pattern == "online-throughput":
            if chars.get("high_throughput"):
                serving_pattern_fit = 0.95
            if family == "epyc":
                serving_pattern_fit = 0.35
        elif serving_pattern in ("batch", "offline-batch"):
            if chars.get("cpu_inference"):
                serving_pattern_fit = 0.95
                reasons.append("serving_pattern batch/offline favors EPYC")
            elif chars.get("pcie_form_factor"):
                serving_pattern_fit = 0.7
            elif chars.get("high_throughput"):
                serving_pattern_fit = 0.55  # capable but not preferred for batch
            if latency_requirement in ("relaxed", "unconstrained"):
                if chars.get("cpu_inference"):
                    serving_pattern_fit = min(1.0, serving_pattern_fit + 0.05)

        # --- locality_fit ---
        locality_fit = 0.5
        if chars.get("data_local") or chars.get("privacy_friendly"):
            locality_fit = 0.9
        if data_locality:
            if chars.get("data_local"):
                locality_fit = 1.0
                reasons.append("satisfies data_locality / privacy-local preference")
            else:
                locality_fit = 0.15
        elif chars.get("rack_scale"):
            locality_fit = 0.35

        # --- evidence_confidence (dimension 0-1; label computed later) ---
        perf_ev = performance_evidence_status(
            self.evidence, meta, model, compute_id, use_case_id
        )
        evidence_conf = evidence_confidence_score(meta, str(perf_ev.get("status") or "NO_DATA"))

        return (
            capability_fit,
            quality_fit,
            performance_fit,
            economic_fit,
            deployment_fit,
            lifecycle_fit,
            serving_pattern_fit,
            locality_fit,
            evidence_conf,
            reasons,
        )

    def _score(
        self,
        *,
        use_case: dict[str, Any],
        use_case_id: str,
        objective: str,
        model: str,
        compute_id: str,
        family: str,
        aim_support: str,
        lifecycle: str,
        level: str,
        utilization: str,
        data_locality: bool,
        capability_fit: float,
        quality_fit: float = 0.5,
        performance_fit: float = 0.5,
        economic_fit: float = 0.5,
        lifecycle_fit: float = 0.5,
        deployment_fit: float = 0.5,
        serving_pattern_fit: float = 0.5,
        locality_fit: float = 0.5,
        evidence_confidence: float = 0.5,
        serving_pattern: str = "interactive",
        latency_requirement: str = "important",
        amd_measured: bool = False,
    ) -> tuple[float, list[str], str, str | None]:
        reasons: list[str] = []
        compute = self.compute.get(compute_id, {})
        chars = compute.get("characteristics") or {}
        meta = self.models.get(model, {})
        size = meta.get("size_class", "unknown")
        rel_cost = compute.get("relative_cost_class", "medium")
        pref_label: str | None = OBJECTIVE_PREF_LABEL.get(objective)
        spec = meta.get("specialization")
        cat = use_case.get("category")
        spec_match = bool(spec and cat and spec == cat)

        score = 0.0
        # AIM maturity (support, not lifecycle)
        score += SUPPORT_RANK.get(aim_support, 0) * 10
        reasons.append(f"AIM support={aim_support}")
        score += LEVEL_ORDER.get(level, 0) * 15

        # Specialization / name hints — weak tie-breakers only (do not dominate evidence)
        if spec_match:
            score += 3
            reasons.append(f"weak specialization hint '{spec}' (tie-breaker)")
        if "coder" in model.lower() and (cat == "coding" or use_case_id.startswith("cod")):
            score += 1

        # Fit-weighted by objective (NOT model size as ranking algorithm)
        if objective == "lowest-cost-sufficient":
            # Constrained flavor in scoring; final LCS ranking uses hw_cost primary
            floor = self._floor_tier(use_case_id)
            tier = self._model_tier(model)
            if tier < floor:
                score -= 80
                reasons.append("incapable: below capability floor")
            else:
                score += capability_fit * 30
                score += quality_fit * 20
                score += economic_fit * 55
                score += performance_fit * 8
                score += lifecycle_fit * 5
                score += serving_pattern_fit * 8
                score += evidence_confidence * 5
                score -= self._hw_cost_rank(compute_id) * 8
                reasons.append("lowest-cost-sufficient: prefer cheaper class that clears floor")
            pref_label = "ECONOMIC_PREFERRED"

        elif objective == "token-cost":
            score += economic_fit * 45
            score += capability_fit * 20
            score += quality_fit * 10
            score += performance_fit * 12
            score += lifecycle_fit * 5
            score += serving_pattern_fit * 5
            score += evidence_confidence * 5
            reasons.append(f"relative cost class={rel_cost}")

        elif objective in ("quality", "throughput"):
            # Quality objective prioritizes quality_fit + evidence over generation bias
            score += quality_fit * 40
            score += capability_fit * 25
            score += performance_fit * 20
            score += evidence_confidence * 15
            score += lifecycle_fit * 8
            score += economic_fit * 4
            score += serving_pattern_fit * 5
            pref_label = "PERFORMANCE_PREFERRED"

        elif objective == "latency":
            score += performance_fit * 35
            if chars.get("local_workstation"):
                score += 25
                reasons.append("local workstation for interactive latency")
                pref_label = "LOCAL_PREFERRED"
            score += capability_fit * 15
            score += quality_fit * 10
            score += lifecycle_fit * 5
            score += evidence_confidence * 5
            if latency_requirement == "critical":
                score += serving_pattern_fit * 10

        elif objective == "edge-local":
            score += capability_fit * 25
            score += quality_fit * 10
            if chars.get("local_workstation") or chars.get("edge_friendly"):
                score += 45
                reasons.append("edge/local/workstation friendly compute")
                pref_label = "WORKSTATION_PREFERRED"
            if data_locality and chars.get("data_local"):
                score += 20
                pref_label = "PRIVACY_PREFERRED"
                reasons.append("data_locality → prefer local Radeon")
            if family == "instinct" and not chars.get("pcie_form_factor"):
                score -= 15
                reasons.append("remote rack Instinct deprioritized for edge-local")
            score += economic_fit * 10
            score += lifecycle_fit * 5
            score += locality_fit * 15
            score += evidence_confidence * 5
            if family == "radeon":
                score += 12

        elif objective == "enterprise":
            score += lifecycle_fit * 30
            score += performance_fit * 22
            score += capability_fit * 20
            score += quality_fit * 15
            score += deployment_fit * 10
            score += evidence_confidence * 10
            if lifecycle != "ga":
                score -= 40
            pref_label = "PRODUCTION_PREFERRED"

        else:  # balanced
            score += capability_fit * 22
            score += quality_fit * 18
            score += performance_fit * 18
            score += economic_fit * 18
            score += lifecycle_fit * 10
            score += deployment_fit * 8
            score += serving_pattern_fit * 8
            score += locality_fit * 5
            score += evidence_confidence * 8
            if utilization == "low" and (
                chars.get("local_workstation")
                or chars.get("cpu_inference")
                or chars.get("pcie_form_factor")
            ):
                score += 18
                reasons.append("balanced@low-traffic: footprint-efficient compute")
            if utilization == "high" and chars.get("high_throughput"):
                score += 18
                reasons.append("balanced@high-traffic: throughput class")
            if utilization == "medium":
                # Mid traffic: do not let very-high HW auto-win on generation alone
                if self._hw_cost_rank(compute_id) >= 5 and economic_fit < 0.35:
                    score -= 12
                    reasons.append("balanced: soft-penalize very-high cost / weak economic_fit")
            # Batch serving: EPYC rises; interactive high-QPS: EPYC does not
            if serving_pattern in ("batch", "offline-batch") and chars.get("cpu_inference"):
                score += 20
                reasons.append("balanced@batch: EPYC fleet utilization")
                pref_label = "BATCH_PREFERRED"
            if (
                serving_pattern == "interactive"
                and utilization == "high"
                and family == "epyc"
            ):
                score -= 25
                reasons.append("balanced: EPYC does not auto-rise for high-concurrency interactive")
            pref_label = pref_label or "BALANCED_PREFERRED"

        # Soft family bias (secondary)
        fam_order = (self.policy.get("objective_compute_bias") or {}).get(objective) or []
        if family in fam_order:
            score += max(0, 8 - fam_order.index(family) * 3)

        # Size bias is soft tie-break only (max ~4)
        size_order = (self.policy.get("objective_size_bias") or {}).get(objective) or []
        if size in size_order:
            score += max(0, 4 - size_order.index(size))

        # INSTINCT generation bias: tiny tie-breaker unless AMD measured evidence present
        gen = INSTINCT_GEN_BIAS.get(compute_id, 0)
        if amd_measured:
            score += gen * 0.5  # measured path may weight generation lightly
        else:
            score += gen * 0.05  # otherwise negligible tie-break only

        # Deployment soft match
        score += deployment_fit * 5

        # Cap unoptimized
        max_unopt = self.policy.get("unoptimized_max_level", "ACCEPTABLE")
        if aim_support == "unoptimized" and LEVEL_ORDER.get(level, 0) > LEVEL_ORDER.get(
            max_unopt, 0
        ):
            reasons.append("capped: unoptimized AIM not promoted above ACCEPTABLE")

        if lifecycle == "tech-preview":
            pref_label = "EVALUATION_PREFERRED"

        cost_confidence = "relative"
        return score, reasons, cost_confidence, pref_label

    def recommend(
        self,
        use_case_id: str,
        objective: str | None = None,
        deployment: str | None = None,
        utilization: str = "medium",
        endpoints: list[dict[str, Any]] | None = None,
        compute_filter: str | None = None,
        show: str = "recommended+supported",
        limit: int | None = None,
        lifecycle_mode: str | None = "production",
        data_locality: bool = False,
        include_excluded: bool = False,
        serving_pattern: str | None = None,
        latency_requirement: str | None = None,
        _keep_pool: bool = False,
    ) -> dict[str, Any]:
        if use_case_id not in self.use_cases:
            raise KeyError(f"unknown use case: {use_case_id}")
        use_case = self.use_cases[use_case_id]
        objective = self.resolve_objective(objective, use_case_id)
        lifecycle_mode = self.resolve_lifecycle_mode(lifecycle_mode)
        allowed = self._allowed_lifecycles(lifecycle_mode)
        serving_pattern = self.resolve_serving_pattern(serving_pattern, use_case_id)
        latency_requirement = self.resolve_latency_requirement(
            use_case_id, serving_pattern, latency_requirement
        )

        candidates: list[Candidate] = []
        excluded: list[Candidate] = []
        locality_exclusions: list[Candidate] = []

        for model in self.aims:
            ok, why, excl_kind = self._capability_ok(
                model, use_case, lifecycle_mode=lifecycle_mode
            )
            if not ok:
                continue
            preferred_models = use_case.get("preferred_models") or []

            for family, compute_id, aim_support, lifecycle in self._aim_cells(model):
                if compute_filter and compute_id != compute_filter and family != compute_filter:
                    continue
                if compute_id not in self.compute:
                    continue

                # Deployment filter
                if deployment:
                    dep = self.compute[compute_id].get("deployment_class") or []
                    if deployment not in dep and not (
                        deployment == "enterprise"
                        and ("datacenter" in dep or "enterprise-server" in dep)
                    ) and not (
                        deployment == "datacenter" and "enterprise" in dep
                    ) and not (
                        deployment in ("workstation", "local", "edge")
                        and any(
                            x in dep
                            for x in (
                                "workstation",
                                "local",
                                "edge",
                                "departmental",
                                "developer",
                            )
                        )
                    ):
                        continue

                production_eligible = lifecycle == "ga"
                lifecycle_ok = lifecycle in allowed

                ov_level, ov_reasons, ov_norm = self._override_level(
                    use_case_id, model, compute_id
                )
                level = ov_level or self._base_level(aim_support, lifecycle)
                if preferred_models and model in preferred_models and not ov_level:
                    level = "PREFERRED"

                (
                    cap_f,
                    qual_f,
                    perf_f,
                    econ_f,
                    dep_f,
                    life_f,
                    serve_f,
                    loc_f,
                    evid_f,
                    fit_reasons,
                ) = self._fits(
                    use_case=use_case,
                    use_case_id=use_case_id,
                    objective=objective,
                    model=model,
                    compute_id=compute_id,
                    family=family,
                    aim_support=aim_support,
                    lifecycle=lifecycle,
                    utilization=utilization,
                    data_locality=data_locality,
                    serving_pattern=serving_pattern,
                    latency_requirement=latency_requirement,
                )

                if objective == "lowest-cost-sufficient":
                    if self._model_tier(model) < self._floor_tier(use_case_id):
                        continue

                meta = self.models.get(model, {})
                perf_ev = performance_evidence_status(
                    self.evidence, meta, model, compute_id, use_case_id
                )
                amd_measured = str(perf_ev.get("status")) == "AMD_MEASURED"
                score, score_reasons, cost_conf, pref_label = self._score(
                    use_case=use_case,
                    use_case_id=use_case_id,
                    objective=objective,
                    model=model,
                    compute_id=compute_id,
                    family=family,
                    aim_support=aim_support,
                    lifecycle=lifecycle,
                    level=level,
                    utilization=utilization,
                    data_locality=data_locality,
                    capability_fit=cap_f,
                    quality_fit=qual_f,
                    performance_fit=perf_f,
                    economic_fit=econ_f,
                    lifecycle_fit=life_f,
                    deployment_fit=dep_f,
                    serving_pattern_fit=serve_f,
                    locality_fit=loc_f,
                    evidence_confidence=evid_f,
                    serving_pattern=serving_pattern,
                    latency_requirement=latency_requirement,
                    amd_measured=amd_measured,
                )
                reasons = ov_reasons + fit_reasons + score_reasons
                conf_label = recommendation_confidence(
                    meta=meta,
                    aim_support=aim_support,
                    lifecycle=lifecycle,
                    level=level,
                    performance_status=str(perf_ev.get("status") or "NO_DATA"),
                    evidence_doc=self.evidence,
                    model=model,
                    use_case_id=use_case_id,
                )
                rationale = {
                    "eligibility": [
                        f"AIM support={aim_support}",
                        f"lifecycle={lifecycle}",
                        f"capability gate ok for {use_case_id}",
                    ],
                    "strengths": [
                        r for r in fit_reasons
                        if "strength" in r.lower()
                        or "clears" in r.lower()
                        or "matches" in r.lower()
                        or "hint" in r.lower()
                        or "favors" in r.lower()
                        or "optimized" in r.lower()
                    ][:6] or reasons[:3],
                    "weaknesses": [
                        r for r in reasons
                        if any(
                            x in r.lower()
                            for x in (
                                "below",
                                "weak",
                                "penal",
                                "pending",
                                "excluded",
                                "capped",
                                "not suited",
                            )
                        )
                    ][:6],
                    "evidence": [
                        f"category={evidence_category_for_model(meta)}",
                        f"maturity={maturity_for_model(meta)}",
                        f"performance_evidence={perf_ev.get('status')}",
                        f"review_status={review_status_for_model(meta)}",
                    ],
                    "uncertainties": [
                        u
                        for u in [
                            perf_ev.get("caveat"),
                            (
                                "AMD comparative performance evidence pending"
                                if not amd_measured
                                else None
                            ),
                            (
                                "Preferred without AMD_MEASURED → confidence capped"
                                if level == "PREFERRED" and not amd_measured
                                else None
                            ),
                        ]
                        if u
                    ],
                }
                if preferred_models and model not in preferred_models:
                    score -= 25
                    reasons.append("not in use-case preferred_models")

                compute = self.compute[compute_id]
                hw_class = compute.get("hardware_cost_class") or compute.get(
                    "relative_cost_class", "medium"
                )
                availability = None
                deployment_channel = None
                if lifecycle in ("preview", "tech-preview"):
                    availability = PRIVATE_EVAL_AVAILABILITY
                    deployment_channel = PRIVATE_EVAL_CHANNEL
                    reasons.append(
                        "available via private eval container "
                        "(Tech Preview / Preview; not production GA)"
                    )
                cand = Candidate(
                    model=model,
                    compute_id=compute_id,
                    family=family,
                    aim_support=aim_support,
                    lifecycle=lifecycle,
                    recommendation=level,
                    score=score,
                    reasons=reasons,
                    cost_confidence=cost_conf,
                    cost_evidence=self._cost_evidence_for(compute_id),
                    relative_cost_class=compute.get("relative_cost_class", "medium"),
                    hardware_cost_class=hw_class,
                    infrastructure_cost_class=hw_class,
                    token_economic_fit=econ_f,
                    override=bool(ov_level),
                    production_eligible=production_eligible,
                    capability_fit=cap_f,
                    quality_fit=qual_f,
                    performance_fit=perf_f,
                    economic_fit=econ_f,
                    deployment_fit=dep_f,
                    lifecycle_fit=life_f,
                    serving_pattern_fit=serve_f,
                    locality_fit=loc_f,
                    evidence_confidence=evid_f,
                    performance_evidence=perf_ev,
                    evidence_badge=str(
                        perf_ev.get("badge")
                        or evidence_badge(evidence_category_for_model(meta))
                    ),
                    rationale=rationale,
                    policy_override=ov_norm,
                    preference_label=pref_label,
                    availability=availability,
                    deployment_channel=deployment_channel,
                    confidence=conf_label,
                )

                if not lifecycle_ok:
                    cand.lifecycle_excluded = True
                    cand.exclusion_kind = "lifecycle"
                    cand.exclusion_reason = (
                        f"lifecycle '{lifecycle}' excluded by mode '{lifecycle_mode}' "
                        f"(allowed={sorted(allowed)})"
                    )
                    cand.matrix_mark = "⊘"
                    excluded.append(cand)
                    if include_excluded:
                        candidates.append(cand)
                    continue

                candidates.append(cand)

        locality_note = None
        if data_locality:
            local_ok = [
                c
                for c in candidates
                if not c.lifecycle_excluded
                and (self.compute[c.compute_id].get("characteristics") or {}).get("data_local")
            ]
            if not local_ok:
                locality_note = "No local candidate satisfies this workload"
            else:
                for c in candidates:
                    chars = self.compute[c.compute_id].get("characteristics") or {}
                    if not chars.get("data_local"):
                        c.score -= 30
                        c.reasons.append("non-local under data_locality constraint")
                        locality_exclusions.append(c)

        ep_index: dict[tuple[str, str], dict[str, Any]] = {}
        for ep in endpoints or []:
            if not ep.get("enabled", True):
                continue
            key = (ep.get("model", ""), ep.get("accelerator", ""))
            ep_index[key] = ep
        for c in candidates:
            ep = ep_index.get((c.model, c.compute_id))
            if ep:
                c.endpoint_available = True
                c.endpoint_id = ep.get("id")

        eligible = [c for c in candidates if not c.lifecycle_excluded]
        rankable = [
            c
            for c in eligible
            if c.recommendation in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE")
        ]

        floor = self._floor_tier(use_case_id)
        if objective == "lowest-cost-sufficient":
            sufficient = [
                c
                for c in rankable
                if self._model_tier(c.model) >= floor and c.capability_fit >= 0.70
            ]
            rankable = sufficient or rankable
            rankable.sort(
                key=lambda c: (
                    self._hw_cost_rank(c.compute_id),
                    -c.economic_fit,
                    self._model_tier(c.model) - floor,
                    -c.score,
                    c.model,
                    c.compute_id,
                )
            )
        elif objective in ("quality", "throughput"):
            # Performance-first: do not let PREFERRED level alone beat higher perf fits
            rankable.sort(
                key=lambda c: (
                    -c.performance_fit,
                    -c.capability_fit,
                    -(
                        1
                        if (self.models.get(c.model, {}).get("specialization")
                            == use_case.get("category"))
                        else 0
                    ),
                    -SUPPORT_RANK.get(c.aim_support, 0),
                    -LEVEL_ORDER.get(c.recommendation, 0),
                    -c.economic_fit,
                    c.model,
                    c.compute_id,
                )
            )
        else:
            rankable.sort(
                key=lambda c: (
                    -LEVEL_ORDER.get(c.recommendation, 0),
                    -c.score,
                    self._hw_cost_rank(c.compute_id),
                    c.model,
                    c.compute_id,
                )
            )
        for i, c in enumerate(rankable, start=1):
            c.rank = i
            if i == 1 and c.preference_label is None:
                c.preference_label = OBJECTIVE_PREF_LABEL.get(objective)
            c.matrix_mark = self._matrix_mark_for(c)
        for c in eligible:
            if c.matrix_mark is None:
                c.matrix_mark = self._matrix_mark_for(c)

        show = (show or "recommended+supported").lower()
        if show in ("recommended", "recommended-only"):
            visible = [c for c in eligible if c.recommendation in ("PREFERRED", "RECOMMENDED")]
        elif show in ("recommended+supported", "recommended-supported"):
            visible = [
                c
                for c in eligible
                if c.recommendation
                in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE", "SUPPORTED")
            ]
        elif show in ("deployed", "deployed-only"):
            visible = [c for c in eligible if c.endpoint_available]
        elif show in ("preferred",):
            visible = [c for c in eligible if c.recommendation == "PREFERRED"]
        elif show in ("all",):
            visible = list(eligible)
            if include_excluded:
                visible = list(candidates)
        else:
            visible = [
                c
                for c in eligible
                if c.recommendation
                in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE", "SUPPORTED")
            ]

        visible.sort(key=lambda c: (c.rank is None, c.rank or 999, -c.score, c.model))
        if limit:
            visible = visible[:limit]

        policy_meta = (self.policy.get("metadata") or {}).get("amd_routing_policy") or {}
        # Keep Candidate objects for card selectors (stripped from public JSON by callers)
        result = {
            "use_case": {
                "id": use_case_id,
                "display_name": use_case.get("display_name", use_case_id),
                "category": use_case.get("category"),
            },
            "objective": objective,
            "utilization": utilization,
            "deployment": deployment,
            "serving_pattern": serving_pattern,
            "latency_requirement": latency_requirement,
            "lifecycle_mode": lifecycle_mode,
            "allowed_lifecycles": sorted(allowed),
            "data_locality": data_locality,
            "locality_note": locality_note,
            "policy_version": policy_meta.get("version", self.policy.get("version")),
            "published": policy_meta.get("published"),
            "cost_data": "relative",
            "cost_evidence_default": "RELATIVE",
            "preference_label": (rankable[0].preference_label if rankable else None),
            "candidates": [c.to_dict() for c in visible],
            "ranked": [c.to_dict() for c in rankable[:20]],
            "lifecycle_exclusions": [c.to_dict() for c in excluded[:30]],
            "locality_soft_exclusions": [
                {
                    "model": c.model,
                    "compute": c.compute_id,
                    "exclusion_kind": "locality",
                    "exclusion_reason": "non-local under data_locality constraint",
                }
                for c in locality_exclusions[:20]
            ],
            "counts": {
                "eligible_cells": len(eligible),
                "ranked": len(rankable),
                "visible": len(visible),
                "deployed": sum(1 for c in eligible if c.endpoint_available),
                "lifecycle_excluded": len(excluded),
            },
        }
        if _keep_pool:
            result["_pool"] = eligible
        return result

    def summary_cards(
        self,
        use_case_id: str,
        *,
        deployment: str | None = None,
        utilization: str = "medium",
        endpoints: list[dict[str, Any]] | None = None,
        lifecycle_mode: str | None = "production",
        data_locality: bool = False,
        serving_pattern: str | None = None,
        latency_requirement: str | None = None,
    ) -> dict[str, Any]:
        """Distinct selectors: PERFORMANCE | BALANCE | LCS (+ optional BATCH/LOCAL)."""
        from token_factory.routing_matrix.selectors import apply_card_selection

        if use_case_id not in self.use_cases:
            raise KeyError(f"unknown use case: {use_case_id}")
        use_case = self.use_cases[use_case_id]
        serving_pattern = self.resolve_serving_pattern(serving_pattern, use_case_id)
        latency_requirement = self.resolve_latency_requirement(
            use_case_id, serving_pattern, latency_requirement
        )
        # Shared eligible pool (fits computed; not one global rank relabeled)
        rec = self.recommend(
            use_case_id,
            objective="balanced",
            deployment=deployment,
            utilization=utilization,
            endpoints=endpoints,
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
            show="all",
            _keep_pool=True,
        )
        pool = list(rec.pop("_pool", None) or [])
        locality_preferred = bool(
            data_locality
            or (use_case.get("optimization_default") == "edge-local")
            or ("local" in ((use_case.get("deployment") or {}).get("typical") or []))
        )
        cards = apply_card_selection(
            self,
            pool,
            use_case=use_case,
            use_case_id=use_case_id,
            utilization=utilization,
            serving_pattern=serving_pattern,
            data_locality=data_locality,
            locality_preferred=locality_preferred,
        )
        return {
            "use_case": use_case_id,
            "lifecycle_mode": self.resolve_lifecycle_mode(lifecycle_mode),
            "serving_pattern": serving_pattern,
            "latency_requirement": latency_requirement,
            "cards": cards,
        }

    def matrix(
        self,
        use_case_id: str,
        objective: str | None = None,
        deployment: str | None = None,
        utilization: str = "medium",
        endpoints: list[dict[str, Any]] | None = None,
        show: str = "all",
        lifecycle_mode: str | None = "production",
        data_locality: bool = False,
        include_excluded: bool = True,
        serving_pattern: str | None = None,
        latency_requirement: str | None = None,
        view_mode: str = "portfolio",
        search: str | None = None,
        vendor: str | None = None,
        compute_group: str | None = "all",
    ) -> dict[str, Any]:
        """Build AIM Portfolio Matrix (default) or Executive View.

        Portfolio: ``rows`` = full merged AIM catalog; ``display_rows`` only after
        explicit Show/search/vendor filters (never silent top-N truncation).
        Executive: may truncate to top-ranked ∪ strategic ∪ private-eval ∪ deployed.
        """
        view_mode = (view_mode or "portfolio").lower()
        if view_mode not in ("portfolio", "executive"):
            view_mode = "portfolio"

        # Scoring/ranking still selective — capability filter applies to recommend().
        result = self.recommend(
            use_case_id,
            objective=objective,
            deployment=deployment,
            utilization=utilization,
            endpoints=endpoints,
            show="all",
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            include_excluded=include_excluded,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
        )
        result.pop("_pool", None)

        # Full compute catalog columns (group toggle filters display only).
        preferred_order = [
            "MI250X",
            "MI300X",
            "MI325X",
            "MI350P",
            "MI350X",
            "MI355X",
            "EPYC_9965",
            "EPYC_ZEN4",
            "EPYC_ZEN5",
            "R9700",
            "W7900",
        ]
        all_cols = [c["id"] for c in self.bundle["compute"].get("compute", [])]
        columns_all = [c for c in preferred_order if c in all_cols]
        columns_all += [c for c in all_cols if c not in columns_all]
        for focus in PRIVATE_EVAL_COMPUTES:
            if focus in all_cols and focus not in columns_all:
                columns_all.append(focus)
        columns = filter_columns(columns_all, self.compute, compute_group)

        cell_sources = list(result["candidates"])
        if include_excluded:
            cell_sources = cell_sources + list(result.get("lifecycle_exclusions") or [])

        # Private-eval enrichment: MI350P / Radeon Preview cells stay visible even
        # when Deployment=enterprise filters workstation Radeon out of recommend().
        pe_result = self.recommend(
            use_case_id,
            objective=objective,
            deployment=None,
            utilization=utilization,
            endpoints=endpoints,
            show="all",
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            include_excluded=True,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
        )
        pe_result.pop("_pool", None)
        pe_sources = list(pe_result["candidates"]) + list(
            pe_result.get("lifecycle_exclusions") or []
        )
        existing_keys = {(c["model"], c["compute"]) for c in cell_sources}
        private_eval_added = []
        for c in pe_sources:
            if c["compute"] not in PRIVATE_EVAL_COMPUTES:
                continue
            if c.get("lifecycle") not in ("preview", "tech-preview"):
                continue
            key = (c["model"], c["compute"])
            if key in existing_keys:
                continue
            c = dict(c)
            c["availability"] = c.get("availability") or PRIVATE_EVAL_AVAILABILITY
            c["deployment_channel"] = (
                c.get("deployment_channel") or PRIVATE_EVAL_CHANNEL
            )
            if not c.get("lifecycle_excluded"):
                reasons = list(c.get("reasons") or [])
                note = (
                    f"matrix private-eval on {c['compute']} "
                    f"(deployment filter '{deployment}' bypassed for display)"
                )
                if deployment and note not in reasons:
                    reasons.append(note)
                    c["reasons"] = reasons
                    c["why"] = reasons
            cell_sources.append(c)
            private_eval_added.append(c)
            existing_keys.add(key)

        scored: dict[tuple[str, str], dict[str, Any]] = {}
        for c in cell_sources:
            scored[(c["model"], c["compute"])] = c

        use_case = self.use_cases[use_case_id]
        catalog_models = catalog_model_ids(self.bundle)
        family_of = {cid: (self.compute.get(cid) or {}).get("family", "") for cid in columns_all}

        ep_index: dict[tuple[str, str], dict[str, Any]] = {}
        for ep in endpoints or []:
            if not ep.get("enabled", True):
                continue
            ep_index[(ep.get("model", ""), ep.get("accelerator", ""))] = ep

        cells: dict[str, dict[str, Any]] = {}
        capability_why: dict[str, str] = {}
        capability_ok_map: dict[str, bool] = {}
        row_status: dict[str, str] = {}
        why_not: dict[str, list[str]] = {}

        for model in catalog_models:
            ok, why, excl_kind = self._capability_ok(
                model, use_case, lifecycle_mode=lifecycle_mode
            )
            capability_ok_map[model] = ok
            capability_why[model] = why if not ok else ""
            meta_bad = metadata_incomplete(self, model) or excl_kind == "metadata_incomplete"
            row_cells: dict[str, Any] = {}

            aim_cells = {
                (fam, cid): (sup, life)
                for fam, cid, sup, life in self._aim_cells(model)
            }

            for compute_id in columns_all:
                family = family_of.get(compute_id) or (
                    self.compute.get(compute_id) or {}
                ).get("family", "")
                key = (model, compute_id)
                if key in scored:
                    cell = dict(scored[key])
                    if not ok:
                        cell["capability_excluded"] = True
                        if cell.get("matrix_mark") in (None, "—"):
                            cell["matrix_mark"] = "◌"
                        reasons = list(cell.get("reasons") or [])
                        note = f"capability_excluded: {why}"
                        if note not in reasons:
                            reasons.insert(0, note)
                            cell["reasons"] = reasons
                            cell["why"] = reasons
                    row_cells[compute_id] = cell
                    continue

                aim = aim_cells.get((family, compute_id))
                if aim is None:
                    # Try any family entry for this compute id
                    aim = next(
                        (v for (f, cid), v in aim_cells.items() if cid == compute_id),
                        None,
                    )
                if aim is None:
                    row_cells[compute_id] = unsupported_cell(
                        model, compute_id, family or "unknown"
                    )
                    continue

                aim_support, lifecycle = aim
                availability = None
                deployment_channel = None
                if lifecycle in ("preview", "tech-preview"):
                    availability = PRIVATE_EVAL_AVAILABILITY
                    deployment_channel = PRIVATE_EVAL_CHANNEL

                if not ok or meta_bad:
                    cell = capability_cell_from_aim(
                        model=model,
                        compute_id=compute_id,
                        family=family or "unknown",
                        aim_support=aim_support,
                        lifecycle=lifecycle,
                        capability_why=why if not ok else "metadata_incomplete",
                        availability=availability,
                        deployment_channel=deployment_channel,
                    )
                else:
                    # AIM support exists but recommend() skipped (e.g. deployment filter).
                    allowed = self._allowed_lifecycles(
                        self.resolve_lifecycle_mode(lifecycle_mode)
                    )
                    life_excl = lifecycle not in allowed
                    level = self._base_level(aim_support, lifecycle)
                    reasons = [
                        f"AIM support={aim_support}",
                        "visible in Portfolio; not in current recommend() filter set",
                    ]
                    if deployment:
                        reasons.append(
                            f"deployment filter '{deployment}' may exclude from ranked candidates"
                        )
                    cell = {
                        "model": model,
                        "compute": compute_id,
                        "family": family or "unknown",
                        "aim_support": aim_support,
                        "lifecycle": lifecycle,
                        "recommendation": level,
                        "rank": None,
                        "score": 0.0,
                        "confidence": "medium",
                        "reasons": reasons,
                        "why": reasons,
                        "endpoint_available": False,
                        "endpoint_id": None,
                        "lifecycle_excluded": life_excl,
                        "capability_excluded": False,
                        "matrix_mark": "⊘" if life_excl else "○",
                        "production_eligible": lifecycle == "ga",
                        "availability": availability,
                        "deployment_channel": deployment_channel,
                        "exclusion_kind": "lifecycle" if life_excl else "deployment",
                        "exclusion_reason": (
                            f"lifecycle '{lifecycle}' excluded by mode "
                            f"'{self.resolve_lifecycle_mode(lifecycle_mode)}'"
                            if life_excl
                            else f"deployment filter '{deployment}'"
                        ),
                    }
                ep = ep_index.get((model, compute_id))
                if ep:
                    cell["endpoint_available"] = True
                    cell["endpoint_id"] = ep.get("id")
                row_cells[compute_id] = cell

            cells[model] = row_cells
            status = classify_row_status(
                model=model,
                cells=row_cells,
                capability_ok=ok and not meta_bad,
                meta_incomplete=meta_bad,
                deployment_filter=deployment,
                compute_meta=self.compute,
            )
            row_status[model] = status
            why_not[model] = why_not_recommended(
                model,
                row_status=status,
                cells=row_cells,
                capability_why=capability_why.get(model) or None,
            )

        ordered = order_portfolio_rows(catalog_models, row_status, cells)
        filtered = filter_display_rows(
            ordered,
            row_status=row_status,
            cells=cells,
            show=show,
            search=search,
            vendor=vendor,
        )

        if view_mode == "executive":
            uc = self.use_cases.get(use_case_id) or {}
            strategic = list(uc.get("preferred_models") or [])
            display_rows = executive_display_rows(
                filtered,
                cells=cells,
                row_status=row_status,
                strategic_models=strategic,
                limit=MATRIX_TOP_ROWS,
            )
            view_label = "Executive View (truncated)"
        else:
            display_rows = filtered
            view_label = "Portfolio Matrix (full catalog)"

        counts = build_catalog_counts(
            catalog_models=catalog_models,
            row_status=row_status,
            cells=cells,
            display_rows=display_rows,
        )
        coverage_warning = None
        if len(display_rows) < len(catalog_models):
            coverage_warning = (
                f"Showing {len(display_rows)} of {len(catalog_models)} catalog models "
                f"({view_label}). Filters or Executive truncation applied — "
                "not a silent catalog omission."
            )

        # Backward-compat candidates: honor original show semantics on scored set
        show_norm = (show or "all").lower()
        if show_norm in ("recommended", "recommended-only"):
            candidates = [
                c
                for c in result["candidates"]
                if c["recommendation"] in ("PREFERRED", "RECOMMENDED")
            ]
        elif show_norm in ("deployed", "deployed-only"):
            candidates = [c for c in result["candidates"] if c.get("endpoint_available")]
        elif show_norm in ("all", "all-aims"):
            candidates = list(result["candidates"])
        else:
            candidates = [
                c
                for c in result["candidates"]
                if c["recommendation"]
                in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE", "SUPPORTED")
            ]

        summaries = self.summary_cards(
            use_case_id,
            deployment=deployment,
            utilization=utilization,
            endpoints=endpoints,
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
        )
        return {
            **{k: result[k] for k in result if k not in ("candidates", "_pool")},
            "view_mode": view_mode,
            "view_label": view_label,
            "columns": columns,
            "columns_all": columns_all,
            "focus_columns": [c for c in columns_all if c in (
                "MI300X", "MI325X", "MI350P", "MI350X", "MI355X",
                "EPYC_9965", "R9700", "W7900",
            )],
            "compute_group": compute_group or "all",
            "rows": list(catalog_models),
            "display_rows": display_rows,
            "row_status": row_status,
            "why_not_recommended": why_not,
            "cells": cells,
            "candidates": candidates,
            "ranked": result["ranked"],
            "summary_cards": summaries["cards"],
            "lifecycle_exclusions": result.get("lifecycle_exclusions") or [],
            "private_eval_matrix_cells": private_eval_added,
            "private_eval_note": (
                "Preview / Tech Preview AIM cells on MI350P, R9700, and W7900 are "
                "available via private eval containers (not silent production GA)."
            ),
            "catalog_counts": counts,
            "compute_counts": build_compute_counts(columns, self.compute),
            "coverage_warning": coverage_warning,
            "show": show,
            "search": search,
            "vendor": vendor,
        }

    def recommend_for_compute(
        self,
        compute_id: str,
        objective: str = "balanced",
        endpoints: list[dict[str, Any]] | None = None,
        lifecycle_mode: str | None = None,
        use_case_id: str | None = None,
    ) -> dict[str, Any]:
        """Invert: given hardware, list best use-case × model fits."""
        if compute_id not in self.compute and compute_id not in {
            c.get("family") for c in self.compute.values()
        }:
            raise KeyError(f"unknown compute: {compute_id}")

        # Default lifecycle for invert: evaluation for TP/preview hardware
        if lifecycle_mode is None:
            if compute_id == "MI350P":
                lifecycle_mode = "evaluation"
            elif compute_id in ("R9700", "W7900"):
                lifecycle_mode = "production-preview"
            else:
                lifecycle_mode = "production"

        use_case_ids = [use_case_id] if use_case_id else list(self.use_cases)
        by_uc = []
        for uc_id in use_case_ids:
            rec = self.recommend(
                uc_id,
                objective=objective,
                endpoints=endpoints,
                compute_filter=compute_id,
                show="recommended+supported",
                limit=5,
                lifecycle_mode=lifecycle_mode,
            )
            if rec["candidates"]:
                by_uc.append(
                    {
                        "use_case": rec["use_case"],
                        "top": rec["ranked"][:3] or rec["candidates"][:3],
                    }
                )
        return {
            "compute": compute_id,
            "objective": objective,
            "lifecycle_mode": self.resolve_lifecycle_mode(lifecycle_mode),
            "use_cases": by_uc,
            "policy_version": (self.policy.get("metadata") or {})
            .get("amd_routing_policy", {})
            .get("version"),
            "escalation_hint": (self.policy.get("escalation") or {}).get(
                "local_to_datacenter"
            ),
        }

    def simulate_route(
        self,
        use_case_id: str,
        objective: str | None = None,
        utilization: str = "medium",
        endpoints: list[dict[str, Any]] | None = None,
        lifecycle_mode: str | None = "production",
        data_locality: bool = False,
        serving_pattern: str | None = None,
        latency_requirement: str | None = None,
    ) -> dict[str, Any]:
        rec = self.recommend(
            use_case_id,
            objective=objective,
            utilization=utilization,
            endpoints=endpoints,
            show="all",
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            include_excluded=False,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
        )
        rec.pop("_pool", None)
        with_excl = self.recommend(
            use_case_id,
            objective=objective,
            utilization=utilization,
            endpoints=endpoints,
            show="all",
            lifecycle_mode=lifecycle_mode,
            data_locality=data_locality,
            include_excluded=True,
            serving_pattern=serving_pattern,
            latency_requirement=latency_requirement,
        )
        with_excl.pop("_pool", None)
        exclusions = with_excl.get("lifecycle_exclusions") or []
        locality_excl = with_excl.get("locality_soft_exclusions") or []
        mi350p_excl = [e for e in exclusions if e.get("compute") == "MI350P"]
        radeon_excl = [e for e in exclusions if e.get("family") == "radeon"]

        ranked = rec["ranked"]
        deployed = [c for c in ranked if c.get("endpoint_available")]
        selected = deployed[0] if deployed else None

        # Serving-pattern / latency soft exclusions (EPYC on high-concurrency interactive)
        serving_excl = [
            c
            for c in ranked
            if c.get("family") == "epyc"
            and rec.get("serving_pattern") == "interactive"
            and utilization == "high"
        ]

        explanation_parts = []
        if selected:
            explanation_parts.append(
                "Highest-ranked currently available eligible endpoint"
            )
        else:
            explanation_parts.append(
                "No deployed endpoint matches eligible recommendations"
            )
        if mi350p_excl:
            explanation_parts.append(
                f"MI350P excluded ({len(mi350p_excl)} cells): lifecycle tech-preview "
                f"not allowed in mode '{rec['lifecycle_mode']}'"
            )
        elif any(c.get("compute") == "MI350P" for c in ranked):
            explanation_parts.append(
                "MI350P eligible under current lifecycle mode (tech-preview allowed)"
            )
        if radeon_excl:
            explanation_parts.append(
                f"Radeon Preview excluded ({len(radeon_excl)} cells): "
                f"lifecycle preview not allowed in mode '{rec['lifecycle_mode']}'"
            )
        if serving_excl:
            explanation_parts.append(
                f"Serving-pattern note: {len(serving_excl)} EPYC candidates deprioritized "
                f"for interactive + high traffic (EPYC is CPU-centric/batch, not a GPU "
                f"interactive competitor); latency={rec.get('latency_requirement')}"
            )
        if locality_excl:
            explanation_parts.append(
                f"Locality: {len(locality_excl)} non-local candidates soft-penalized"
            )
        if rec.get("locality_note"):
            explanation_parts.append(rec["locality_note"])

        return {
            "use_case": rec["use_case"],
            "objective": rec["objective"],
            "utilization": utilization,
            "serving_pattern": rec.get("serving_pattern"),
            "latency_requirement": rec.get("latency_requirement"),
            "lifecycle_mode": rec["lifecycle_mode"],
            "allowed_lifecycles": rec["allowed_lifecycles"],
            "eligible_combinations": rec["counts"]["eligible_cells"],
            "amd_recommendation": ranked[:5],
            "currently_deployed_eligible": deployed[:5],
            "selected_runtime_route": selected,
            "lifecycle_exclusions": exclusions[:20],
            "serving_pattern_exclusions": serving_excl[:10],
            "locality_exclusions": locality_excl[:10],
            "exclusions": {
                "lifecycle": exclusions[:20],
                "serving_pattern_latency": serving_excl[:10],
                "locality": locality_excl[:10],
            },
            "explanation": "; ".join(explanation_parts),
            "locality_note": rec.get("locality_note"),
            "policy_version": rec["policy_version"],
            "cost_data": rec["cost_data"],
        }

    def compare_models(
        self,
        use_case_id: str,
        model_a: str,
        model_b: str,
        *,
        compute_id: str | None = None,
        objective: str | None = None,
        lifecycle_mode: str | None = "production",
        serving_pattern: str | None = None,
        utilization: str = "medium",
    ) -> dict[str, Any]:
        """Structured model-vs-model comparison for a use case (explainable, no fabricated wins)."""
        if use_case_id not in self.use_cases:
            raise KeyError(f"unknown use case: {use_case_id}")
        from token_factory.routing_matrix.loader import normalize_model_id as _norm

        model_a = _norm(model_a, self.model_aliases)
        model_b = _norm(model_b, self.model_aliases)

        rec = self.recommend(
            use_case_id,
            objective=objective,
            compute_filter=compute_id,
            lifecycle_mode=lifecycle_mode,
            serving_pattern=serving_pattern,
            utilization=utilization,
            show="all",
        )
        def _pick(mid: str) -> dict[str, Any] | None:
            pool = rec.get("ranked") or rec.get("candidates") or []
            matches = [c for c in pool if c.get("model") == mid]
            if compute_id:
                matches = [c for c in matches if c.get("compute") == compute_id]
            return matches[0] if matches else None

        ca, cb = _pick(model_a), _pick(model_b)
        meta_a = self.models.get(model_a) or {}
        meta_b = self.models.get(model_b) or {}
        use_case = self.use_cases[use_case_id]

        def _cap_row(meta: dict[str, Any], key: str) -> str:
            caps = meta.get("capabilities") or {}
            from token_factory.routing_matrix.evidence import cap_truth

            t = cap_truth(caps.get(key))
            return {"true": "✓", "false": "✗", "unknown": "?"}.get(t, "?")

        def _strength(meta: dict[str, Any], key: str) -> str:
            return strength_level(meta, key)

        dimensions = {
            "capability_coding": {
                model_a: _cap_row(meta_a, "coding"),
                model_b: _cap_row(meta_b, "coding"),
            },
            "capability_reasoning": {
                model_a: _cap_row(meta_a, "reasoning"),
                model_b: _cap_row(meta_b, "reasoning"),
            },
            "capability_long_context": {
                model_a: _cap_row(meta_a, "long_context"),
                model_b: _cap_row(meta_b, "long_context"),
            },
            "capability_agentic_coding": {
                model_a: _cap_row(meta_a, "agentic_coding"),
                model_b: _cap_row(meta_b, "agentic_coding"),
            },
            "strength_agentic_coding": {
                model_a: _strength(meta_a, "agentic_coding"),
                model_b: _strength(meta_b, "agentic_coding"),
            },
            "strength_repository_reasoning": {
                model_a: _strength(meta_a, "repository_reasoning"),
                model_b: _strength(meta_b, "repository_reasoning"),
            },
            "strength_general_reasoning": {
                model_a: _strength(meta_a, "general_reasoning"),
                model_b: _strength(meta_b, "general_reasoning"),
            },
            "strength_long_context": {
                model_a: _strength(meta_a, "long_context"),
                model_b: _strength(meta_b, "long_context"),
            },
        }

        aim_a = (ca or {}).get("aim_support")
        aim_b = (cb or {}).get("aim_support")
        if not ca or not cb:
            # fall back to AIM cells if filtered out of ranked
            for mid, slot in ((model_a, "a"), (model_b, "b")):
                cells = self._aim_cells(mid)
                pick = None
                if compute_id:
                    pick = next((x for x in cells if x[1] == compute_id), None)
                if not pick and cells:
                    pick = cells[0]
                if slot == "a" and not aim_a and pick:
                    aim_a = pick[2]
                if slot == "b" and not aim_b and pick:
                    aim_b = pick[2]

        pe_a = (ca or {}).get("performance_evidence") or performance_evidence_status(
            self.evidence, meta_a, model_a, compute_id or "MI355X", use_case_id
        )
        pe_b = (cb or {}).get("performance_evidence") or performance_evidence_status(
            self.evidence, meta_b, model_b, compute_id or "MI355X", use_case_id
        )

        why_a_over_b: list[str] = []
        why_b_over_a: list[str] = []
        if ca and cb:
            if (ca.get("rank") or 999) < (cb.get("rank") or 999):
                why_a_over_b.append(
                    f"Ranks higher under objective={rec.get('objective')} "
                    f"(#{ca.get('rank')} vs #{cb.get('rank')})"
                )
            elif (cb.get("rank") or 999) < (ca.get("rank") or 999):
                why_b_over_a.append(
                    f"Ranks higher under objective={rec.get('objective')} "
                    f"(#{cb.get('rank')} vs #{ca.get('rank')})"
                )
            if (ca.get("quality_fit") or 0) > (cb.get("quality_fit") or 0) + 0.05:
                why_a_over_b.append(
                    f"Higher quality_fit ({ca.get('quality_fit')} vs {cb.get('quality_fit')})"
                )
            if (cb.get("quality_fit") or 0) > (ca.get("quality_fit") or 0) + 0.05:
                why_b_over_a.append(
                    f"Higher quality_fit ({cb.get('quality_fit')} vs {ca.get('quality_fit')})"
                )
            if ca.get("override") and not cb.get("override"):
                why_a_over_b.append("Explicit policy override present")
            if cb.get("override") and not ca.get("override"):
                why_b_over_a.append("Explicit policy override present")
        elif ca and not cb:
            why_a_over_b.append(f"{model_b} not in eligible ranked set for this filter")
        elif cb and not ca:
            why_b_over_a.append(f"{model_a} not in eligible ranked set for this filter")

        caveat = (
            "AMD comparative performance evidence is not yet available for this pair; "
            "differences reflect capability metadata, AIM support, and policy — not measured AMD superiority."
        )
        if pe_a.get("status") == "AMD_MEASURED" and pe_b.get("status") == "AMD_MEASURED":
            caveat = "Both sides have AMD_MEASURED evidence on file."

        preferred = None
        if ca and cb:
            if (ca.get("rank") or 999) <= (cb.get("rank") or 999):
                preferred = {
                    "model": model_a,
                    "recommendation": ca.get("recommendation"),
                    "confidence": ca.get("confidence"),
                    "compute": ca.get("compute"),
                }
            else:
                preferred = {
                    "model": model_b,
                    "recommendation": cb.get("recommendation"),
                    "confidence": cb.get("confidence"),
                    "compute": cb.get("compute"),
                }

        return {
            "use_case": use_case_id,
            "compute": compute_id,
            "objective": rec.get("objective"),
            "lifecycle_mode": rec.get("lifecycle_mode"),
            "policy_version": rec.get("policy_version"),
            "models": {
                model_a: {
                    "candidate": ca,
                    "capabilities": meta_a.get("capabilities"),
                    "strengths": meta_a.get("strengths"),
                    "evidence": meta_a.get("evidence"),
                    "aim_support": aim_a,
                    "performance_evidence": pe_a,
                },
                model_b: {
                    "candidate": cb,
                    "capabilities": meta_b.get("capabilities"),
                    "strengths": meta_b.get("strengths"),
                    "evidence": meta_b.get("evidence"),
                    "aim_support": aim_b,
                    "performance_evidence": pe_b,
                },
            },
            "dimensions": dimensions,
            "aim_support": {model_a: aim_a, model_b: aim_b},
            "amd_performance_evidence": {
                model_a: pe_a.get("status"),
                model_b: pe_b.get("status"),
            },
            "why_a_over_b": why_a_over_b,
            "why_b_over_a": why_b_over_a,
            "policy_preference": preferred,
            "caveat": caveat,
            "language_note": "Avoid Best/Winner/Superior — this is a policy comparison with evidence status.",
        }

    def evidence_audit(self) -> dict[str, Any]:
        """Audit model provenance + evidence catalog coverage."""
        models = list(self.models.values())
        gaps = audit_evidence_gaps(models, self.evidence)
        verified = [
            m["model"]
            for m in models
            if review_status_for_model(m) == "verified"
        ]
        return {
            "policy_version": (self.policy.get("metadata") or {})
            .get("amd_routing_policy", {})
            .get("version")
            or self.policy.get("policy", {}).get("policy_version"),
            "model_count": len(models),
            "evidence_records": len(self.evidence.get("records") or []),
            "amd_measurements": self.evidence.get("amd_measurements"),
            "verified_models": verified,
            "gaps": gaps,
            "statement": (
                "Token Factory recommendations are policy decisions derived from model "
                "capability, AMD AIM support, deployment requirements, lifecycle, economics, "
                "and available performance evidence. Missing evidence lowers recommendation "
                "confidence and should not be interpreted as proof of inferiority."
            ),
        }

    def evidence_gaps(self) -> dict[str, Any]:
        return audit_evidence_gaps(list(self.models.values()), self.evidence)

    def policy_audit(
        self,
        *,
        use_case_id: str | None = None,
        lifecycle_mode: str = "production",
    ) -> dict[str, Any]:
        """Flag Preferred + low evidence / specialization-only style wins."""
        targets = [use_case_id] if use_case_id else [
            u for u in self.use_cases if str(self.use_cases[u].get("category")) == "coding"
        ][:8] or list(self.use_cases)[:5]
        findings: list[dict[str, Any]] = []
        for uc in targets:
            if uc not in self.use_cases:
                continue
            rec = self.recommend(uc, lifecycle_mode=lifecycle_mode, show="recommended")
            for c in (rec.get("ranked") or [])[:5]:
                issues: list[str] = []
                if c.get("recommendation") == "PREFERRED" and str(c.get("confidence")).lower() in (
                    "low",
                    "experimental",
                    "medium",
                ):
                    pe = (c.get("performance_evidence") or {}).get("status")
                    if pe != "AMD_MEASURED":
                        issues.append("PREFERRED without AMD_MEASURED evidence")
                    if str(c.get("confidence")).lower() != "high":
                        issues.append(f"confidence={c.get('confidence')} (not High)")
                reasons = " ".join(c.get("reasons") or []).lower()
                if "specialization" in reasons and "amd_measured" not in reasons:
                    if (c.get("quality_fit") or 0) < 0.6:
                        issues.append("specialization hint without strong quality_fit")
                if issues:
                    findings.append(
                        {
                            "use_case": uc,
                            "model": c.get("model"),
                            "compute": c.get("compute"),
                            "recommendation": c.get("recommendation"),
                            "confidence": c.get("confidence"),
                            "evidence_badge": c.get("evidence_badge"),
                            "issues": issues,
                        }
                    )
        return {
            "policy_version": rec.get("policy_version") if targets else None,
            "findings": findings,
            "finding_count": len(findings),
        }


def recommend(**kwargs: Any) -> dict[str, Any]:
    return RecommendationEngine().recommend(**kwargs)


def simulate_route(**kwargs: Any) -> dict[str, Any]:
    return RecommendationEngine().simulate_route(**kwargs)
