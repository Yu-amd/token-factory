"""Evidence governance helpers for policy-quality recommendations.

Token Factory recommendations are policy decisions derived from model capability,
AMD AIM support, deployment requirements, lifecycle, economics, and available
performance evidence. Missing evidence lowers recommendation confidence and
should not be interpreted as proof of inferiority.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from token_factory.runtime.paths import repo_root

# Source / confidence categories (uppercase canonical)
EVIDENCE_CATEGORIES = (
    "VERIFIED",
    "PUBLIC_EVAL",
    "MODEL_CARD",
    "AMD_MEASURED",
    "AMD_ESTIMATED",
    "INFERRED",
    "UNKNOWN",
)

# Evidence maturity E0–E4
MATURITY = {
    "E0": "Unknown",
    "E1": "Inferred",
    "E2": "Official model documentation",
    "E3": "Public validated evaluation",
    "E4": "AMD measured",
}

CATEGORY_TO_MATURITY = {
    "UNKNOWN": "E0",
    "INFERRED": "E1",
    "MODEL_CARD": "E2",
    "PUBLIC_EVAL": "E3",
    "VERIFIED": "E3",
    "AMD_ESTIMATED": "E3",
    "AMD_MEASURED": "E4",
}

PERFORMANCE_EVIDENCE_STATUS = (
    "AMD_MEASURED",
    "PUBLIC_ONLY",
    "ESTIMATED",
    "NO_DATA",
)

RECOMMENDATION_CONFIDENCE = ("High", "Medium", "Low", "Experimental")

STRENGTH_LEVELS = ("unknown", "low", "medium", "high", "very-high")
STRENGTH_SCORE = {
    "unknown": 0.0,
    "low": 0.25,
    "medium": 0.5,
    "high": 0.75,
    "very-high": 1.0,
}

# Use-case category / id → relevant strength keys for quality_fit
USE_CASE_STRENGTHS: dict[str, tuple[str, ...]] = {
    "code-completion": ("code_completion", "code_generation"),
    "coding-assistant": ("code_generation", "agentic_coding", "code_completion"),
    "code-generation": ("code_generation", "code_completion"),
    "code-review": ("code_review", "repository_reasoning", "general_reasoning"),
    "repository-reasoning": ("repository_reasoning", "agentic_coding", "long_context"),
    "software-engineering-agent": (
        "agentic_coding",
        "repository_reasoning",
        "terminal_tasks",
        "code_generation",
    ),
    "general-reasoning": ("general_reasoning",),
    "math-reasoning": ("general_reasoning",),
    "long-context-rag": ("long_context",),
    "rag-complex": ("long_context", "general_reasoning"),
    "tool-use-agent": ("agentic_coding", "terminal_tasks"),
    "coding": ("code_generation", "agentic_coding", "code_completion"),
    "reasoning": ("general_reasoning",),
}

EVIDENCE_BADGE = {
    "AMD_MEASURED": "AMD",
    "AMD_ESTIMATED": "AMD~",
    "PUBLIC_EVAL": "PUB",
    "VERIFIED": "PUB",
    "MODEL_CARD": "CARD",
    "INFERRED": "INF",
    "UNKNOWN": "?",
    "PUBLIC_ONLY": "PUB",
    "ESTIMATED": "AMD~",
    "NO_DATA": "?",
}


def load_evidence_catalog(root: Path | None = None) -> dict[str, Any]:
    """Load catalog/evidence.yaml (empty-safe)."""
    path = (root or repo_root()) / "catalog" / "evidence.yaml"
    if not path.exists():
        return {
            "version": "1",
            "metadata": {},
            "records": [],
            "amd_measurements": None,
            "cost_evidence": [],
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a mapping")
    data.setdefault("records", [])
    data.setdefault("amd_measurements", None)
    data.setdefault("cost_evidence", [])
    return data


def normalize_category(raw: Any) -> str:
    if raw is None:
        return "UNKNOWN"
    s = str(raw).strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "PUBLICEVAL": "PUBLIC_EVAL",
        "PUBLIC": "PUBLIC_EVAL",
        "MODELCARD": "MODEL_CARD",
        "AMDMEASURED": "AMD_MEASURED",
        "AMDESTIMATED": "AMD_ESTIMATED",
        "PENDING": "UNKNOWN",
    }
    s = aliases.get(s, s)
    return s if s in EVIDENCE_CATEGORIES else "UNKNOWN"


def cap_truth(value: Any) -> str:
    """Normalize capability to tri-state: true | false | unknown."""
    if value is True or value == "true" or value == "supported":
        return "true"
    if value is False or value == "false" or value == "unsupported":
        return "false"
    return "unknown"


def cap_is_true(value: Any) -> bool:
    return cap_truth(value) == "true"


def cap_is_false(value: Any) -> bool:
    return cap_truth(value) == "false"


def cap_is_unknown(value: Any) -> bool:
    return cap_truth(value) == "unknown"


def strength_level(meta: dict[str, Any], key: str) -> str:
    strengths = meta.get("strengths") or meta.get("workload_strengths") or {}
    raw = strengths.get(key, "unknown")
    s = str(raw).lower().replace("_", "-")
    if s in STRENGTH_LEVELS:
        return s
    return "unknown"


def evidence_category_for_model(meta: dict[str, Any]) -> str:
    evidence = meta.get("evidence") or {}
    for key in (
        "quality_evidence",
        "capability_confidence_category",
        "category",
        "source_type",
    ):
        if evidence.get(key):
            return normalize_category(evidence.get(key))
    prov = meta.get("provenance") or {}
    method = str(prov.get("method") or "").lower()
    if "model-card" in method or "model_card" in method or "official" in method:
        return "MODEL_CARD"
    if "public" in method or "eval" in method:
        return "PUBLIC_EVAL"
    if "infer" in method or "model-id" in method:
        return "INFERRED"
    conf = str(prov.get("confidence") or evidence.get("capability_confidence") or "").lower()
    if conf == "high":
        return "VERIFIED"
    if conf == "medium":
        return "MODEL_CARD"
    return "INFERRED"


def maturity_for_model(meta: dict[str, Any]) -> str:
    evidence = meta.get("evidence") or {}
    explicit = evidence.get("maturity") or meta.get("evidence_maturity")
    if explicit in MATURITY:
        return str(explicit)
    return CATEGORY_TO_MATURITY.get(evidence_category_for_model(meta), "E0")


def review_status_for_model(meta: dict[str, Any]) -> str:
    evidence = meta.get("evidence") or {}
    status = (
        evidence.get("review_status")
        or (meta.get("provenance") or {}).get("review_status")
        or "needs-review"
    )
    s = str(status).lower()
    if s in ("verified", "provisional", "needs-review"):
        return s
    return "needs-review"


def records_for_model(
    evidence_doc: dict[str, Any], model: str, *, workload: str | None = None
) -> list[dict[str, Any]]:
    out = []
    for rec in evidence_doc.get("records") or []:
        if rec.get("model") != model:
            continue
        if workload and rec.get("workload") not in (None, workload, "general"):
            # allow records tagged for the use-case or coding family
            w = str(rec.get("workload") or "")
            if workload not in w and w not in workload:
                if not (
                    workload.startswith("cod")
                    and w
                    in (
                        "coding",
                        "coding-assistant",
                        "agentic_coding",
                        "code_generation",
                    )
                ):
                    continue
        out.append(rec)
    return out


def has_amd_measured(
    evidence_doc: dict[str, Any],
    model: str,
    *,
    compute_id: str | None = None,
    workload: str | None = None,
) -> bool:
    for rec in records_for_model(evidence_doc, model, workload=workload):
        if normalize_category(rec.get("confidence") or rec.get("source_type")) != "AMD_MEASURED":
            continue
        if compute_id and rec.get("compute") and rec.get("compute") != compute_id:
            continue
        return True
    amd = evidence_doc.get("amd_measurements")
    if isinstance(amd, list):
        for row in amd:
            if row and row.get("model") == model:
                if compute_id and row.get("compute") and row.get("compute") != compute_id:
                    continue
                return True
    return False


def performance_evidence_status(
    evidence_doc: dict[str, Any],
    meta: dict[str, Any],
    model: str,
    compute_id: str,
    use_case_id: str,
) -> dict[str, Any]:
    """Return status AMD_MEASURED|PUBLIC_ONLY|ESTIMATED|NO_DATA for model×compute×workload."""
    if has_amd_measured(evidence_doc, model, compute_id=compute_id, workload=use_case_id):
        return {
            "status": "AMD_MEASURED",
            "source": "catalog/evidence.yaml",
            "badge": "AMD",
        }
    evidence = meta.get("evidence") or {}
    amd_status = str(evidence.get("amd_performance_evidence") or "pending").lower()
    if amd_status in ("measured", "amd_measured", "amd-measured"):
        return {"status": "AMD_MEASURED", "source": "model.evidence", "badge": "AMD"}
    if amd_status in ("estimated", "amd_estimated", "amd-estimated"):
        return {"status": "ESTIMATED", "source": "model.evidence", "badge": "AMD~"}

    public_recs = [
        r
        for r in records_for_model(evidence_doc, model, workload=use_case_id)
        if normalize_category(r.get("confidence") or r.get("source_type"))
        in ("PUBLIC_EVAL", "VERIFIED", "MODEL_CARD")
    ]
    if public_recs or evidence_category_for_model(meta) in (
        "PUBLIC_EVAL",
        "VERIFIED",
        "MODEL_CARD",
    ):
        return {
            "status": "PUBLIC_ONLY",
            "source": public_recs[0].get("source") if public_recs else "model provenance",
            "badge": "PUB",
            "caveat": "AMD comparative performance evidence pending",
        }
    return {
        "status": "NO_DATA",
        "source": None,
        "badge": "?",
        "caveat": "No task performance evidence on file",
    }


def recommendation_confidence(
    *,
    meta: dict[str, Any],
    aim_support: str,
    lifecycle: str,
    level: str,
    performance_status: str,
    evidence_doc: dict[str, Any],
    model: str,
    use_case_id: str,
) -> str:
    """High|Medium|Low|Experimental per policy evidence rules.

    High requires AMD_MEASURED (or multiple verified sources) plus mature AIM + GA.
    """
    if lifecycle in ("preview", "tech-preview") or aim_support == "preview":
        return "Experimental"
    if review_status_for_model(meta) == "needs-review" and maturity_for_model(meta) in (
        "E0",
        "E1",
    ):
        if level == "PREFERRED":
            return "Low"
        return "Experimental" if lifecycle != "ga" else "Low"

    cat = evidence_category_for_model(meta)
    has_amd = performance_status == "AMD_MEASURED" or has_amd_measured(
        evidence_doc, model, workload=use_case_id
    )
    verified_sources = [
        r
        for r in records_for_model(evidence_doc, model, workload=use_case_id)
        if normalize_category(r.get("confidence") or r.get("source_type"))
        in ("VERIFIED", "PUBLIC_EVAL", "MODEL_CARD", "AMD_MEASURED")
    ]
    multi_verified = len({r.get("source") for r in verified_sources if r.get("source")}) >= 2

    if (
        has_amd
        and aim_support == "optimized"
        and lifecycle == "ga"
        and cat in ("VERIFIED", "PUBLIC_EVAL", "MODEL_CARD", "AMD_MEASURED")
    ):
        return "High"
    if multi_verified and aim_support == "optimized" and lifecycle == "ga" and has_amd:
        return "High"

    # Preferred without AMD measured evidence cannot be High
    if level == "PREFERRED" and not has_amd:
        if cat in ("PUBLIC_EVAL", "MODEL_CARD", "VERIFIED") and aim_support in (
            "optimized",
            "general",
        ):
            return "Medium"
        return "Low"

    if cat in ("PUBLIC_EVAL", "MODEL_CARD", "VERIFIED") and aim_support == "optimized":
        return "Medium"
    if cat == "INFERRED" or performance_status == "NO_DATA":
        return "Low"
    return "Medium"


def quality_fit_from_strengths(
    meta: dict[str, Any],
    use_case_id: str,
    use_case: dict[str, Any],
) -> tuple[float, list[str]]:
    """Derive quality_fit from workload strengths + weak specialization hint."""
    reasons: list[str] = []
    keys = list(USE_CASE_STRENGTHS.get(use_case_id) or ())
    cat = use_case.get("category")
    if cat and cat in USE_CASE_STRENGTHS and not keys:
        keys = list(USE_CASE_STRENGTHS[cat])
    if not keys:
        # Generic: prefer general_reasoning / code_generation lightly
        keys = ["general_reasoning", "code_generation"]

    scores = [STRENGTH_SCORE.get(strength_level(meta, k), 0.0) for k in keys]
    known = [s for s in scores if s > 0]
    if known:
        fit = sum(known) / len(keys)
        top = max(
            ((k, strength_level(meta, k)) for k in keys),
            key=lambda pair: STRENGTH_SCORE.get(pair[1], 0.0),
        )
        if STRENGTH_SCORE.get(top[1], 0.0) >= 0.75:
            reasons.append(f"workload strength {top[0]}={top[1]}")
    else:
        fit = 0.45
        reasons.append("no workload strengths on file (neutral quality_fit)")

    # Weak specialization hint (tie-breaker scale)
    spec = meta.get("specialization")
    if spec and cat and spec == cat:
        fit = min(1.0, fit + 0.04)
        reasons.append(f"weak specialization hint '{spec}'")

    # Name heuristic — weak only
    model_id = str(meta.get("model") or "")
    if "coder" in model_id.lower() and (cat == "coding" or use_case_id.startswith("cod")):
        fit = min(1.0, fit + 0.02)
        reasons.append("weak name hint 'Coder' in model id")

    return max(0.0, min(1.0, fit)), reasons


def evidence_confidence_score(meta: dict[str, Any], performance_status: str) -> float:
    """0–1 dimension for ranking (not recommendation High/Medium label)."""
    maturity = maturity_for_model(meta)
    base = {"E0": 0.15, "E1": 0.35, "E2": 0.55, "E3": 0.75, "E4": 0.95}.get(maturity, 0.3)
    if performance_status == "AMD_MEASURED":
        base = max(base, 0.95)
    elif performance_status == "PUBLIC_ONLY":
        base = max(base, 0.6)
    elif performance_status == "ESTIMATED":
        base = max(base, 0.5)
    elif performance_status == "NO_DATA":
        base = min(base, 0.4)
    return base


def normalize_override(cell: dict[str, Any] | None) -> dict[str, Any] | None:
    """Ensure policy overrides expose auditable governance fields."""
    if not cell:
        return None
    rationale = cell.get("rationale") or []
    if isinstance(rationale, str):
        rationale = [rationale]
    return {
        "decision": cell.get("recommendation") or cell.get("decision"),
        "rationale": list(rationale),
        "owner": cell.get("owner") or cell.get("policy_owner") or "amd-routing-policy",
        "reviewed": cell.get("reviewed") or cell.get("reviewed_at"),
        "expires": cell.get("expires"),
        "raw": cell,
    }


def audit_evidence_gaps(
    models: list[dict[str, Any]],
    evidence_doc: dict[str, Any],
) -> dict[str, Any]:
    """Summarize missing AMD measured data and incomplete provenance."""
    gaps: list[dict[str, Any]] = []
    for meta in models:
        model = meta.get("model")
        if not model:
            continue
        amd = (meta.get("evidence") or {}).get("amd_performance_evidence", "pending")
        if str(amd).lower() in ("pending", "none", "unknown", ""):
            if not has_amd_measured(evidence_doc, model):
                gaps.append(
                    {
                        "model": model,
                        "gap": "amd_performance_evidence_pending",
                        "maturity": maturity_for_model(meta),
                        "review_status": review_status_for_model(meta),
                    }
                )
        prov = meta.get("provenance") or {}
        sources = prov.get("sources") or []
        if not sources:
            gaps.append(
                {
                    "model": model,
                    "gap": "missing_provenance_sources",
                    "maturity": maturity_for_model(meta),
                    "review_status": review_status_for_model(meta),
                }
            )
        for key, val in (meta.get("capabilities") or {}).items():
            if cap_is_unknown(val):
                gaps.append(
                    {
                        "model": model,
                        "gap": f"capability_unknown:{key}",
                        "maturity": maturity_for_model(meta),
                        "review_status": review_status_for_model(meta),
                    }
                )
    return {
        "gap_count": len(gaps),
        "gaps": gaps,
        "amd_measurements_present": bool(evidence_doc.get("amd_measurements")),
        "record_count": len(evidence_doc.get("records") or []),
        "as_of": date.today().isoformat(),
    }


def evidence_badge(category_or_status: str) -> str:
    return EVIDENCE_BADGE.get(normalize_category(category_or_status), EVIDENCE_BADGE.get(category_or_status, "?"))
