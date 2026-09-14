"""AIM Portfolio Matrix helpers — full catalog rows, explicit filters, row status.

Portfolio (default): every canonical AIM model is a row; no silent top-N truncation.
Executive: may truncate to top-ranked ∪ strategic ∪ private-eval ∪ deployed.
"""

from __future__ import annotations

from typing import Any

AMD_DOCS_MODELS_URL = (
    "https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html"
)

ROW_STATUS = (
    "recommended",
    "suitable",
    "supported",
    "capability_excluded",
    "lifecycle_excluded",
    "deployment_excluded",
    "no_supported_compute",
    "metadata_incomplete",
)

# Portfolio display ordering (lower = earlier)
_STATUS_ORDER = {
    "recommended": 0,
    "suitable": 1,
    "supported": 2,
    "lifecycle_excluded": 3,
    "deployment_excluded": 4,
    "capability_excluded": 5,
    "no_supported_compute": 6,
    "metadata_incomplete": 7,
}

EXECUTIVE_TOP_ROWS = 14
FOCUS_COMPUTES = (
    "MI300X",
    "MI325X",
    "MI350P",
    "MI350X",
    "MI355X",
    "EPYC_9965",
    "R9700",
    "W7900",
)
PRIVATE_EVAL_COMPUTES = ("MI350P", "R9700", "W7900")


def vendor_of(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return model


def catalog_model_ids(bundle: dict[str, Any]) -> list[str]:
    """Canonical model ids from merged AIM catalog (aims.yaml ∪ tech-preview)."""
    return sorted({a["model"] for a in (bundle.get("aims") or {}).get("aims") or []})


def metadata_incomplete(engine: Any, model: str) -> bool:
    """True when AIM exists but models.yaml capability metadata is missing/unusable."""
    meta = engine.models.get(model)
    if not meta:
        return True
    caps = meta.get("capabilities")
    if not isinstance(caps, dict) or not caps:
        return True
    # Unknown on core text_generation is incomplete
    tg = caps.get("text_generation")
    if tg is None:
        return True
    from token_factory.routing_matrix.evidence import cap_is_unknown

    if cap_is_unknown(tg):
        return True
    return False


def unsupported_cell(
    model: str,
    compute_id: str,
    family: str,
    *,
    why: str | None = None,
) -> dict[str, Any]:
    """No AIM support on this compute — the only case that uses mark '—'."""
    reasons = [why or f"No AIM support for {model} on {compute_id}"]
    return {
        "model": model,
        "compute": compute_id,
        "family": family,
        "aim_support": None,
        "lifecycle": None,
        "recommendation": "NOT_SUPPORTED",
        "rank": None,
        "score": 0.0,
        "confidence": "unknown",
        "reasons": reasons,
        "why": reasons,
        "endpoint_available": False,
        "endpoint_id": None,
        "lifecycle_excluded": False,
        "capability_excluded": False,
        "matrix_mark": "—",
        "production_eligible": False,
        "availability": None,
        "deployment_channel": None,
    }


def capability_cell_from_aim(
    *,
    model: str,
    compute_id: str,
    family: str,
    aim_support: str,
    lifecycle: str,
    capability_why: str,
    availability: str | None = None,
    deployment_channel: str | None = None,
) -> dict[str, Any]:
    """AIM support exists but model fails use-case capabilities — not '—'."""
    reasons = [f"capability_excluded: {capability_why}"]
    return {
        "model": model,
        "compute": compute_id,
        "family": family,
        "aim_support": aim_support,
        "lifecycle": lifecycle,
        "recommendation": "SUPPORTED",
        "rank": None,
        "score": 0.0,
        "confidence": "low",
        "reasons": reasons,
        "why": reasons,
        "endpoint_available": False,
        "endpoint_id": None,
        "lifecycle_excluded": False,
        "capability_excluded": True,
        "matrix_mark": "◌",
        "production_eligible": lifecycle == "ga",
        "availability": availability,
        "deployment_channel": deployment_channel,
    }


def classify_row_status(
    *,
    model: str,
    cells: dict[str, Any],
    capability_ok: bool,
    meta_incomplete: bool,
    deployment_filter: str | None,
    compute_meta: dict[str, Any],
) -> str:
    """Derive a single row_status for Portfolio ordering / coverage."""
    del model  # status is derived from cells / flags
    if meta_incomplete:
        return "metadata_incomplete"

    support_cells = [
        c
        for c in cells.values()
        if c and c.get("aim_support") is not None and c.get("matrix_mark") != "—"
    ]
    if not support_cells:
        return "no_supported_compute"

    if not capability_ok:
        return "capability_excluded"

    # Deployment exclusion: AIM cells exist but none match deployment class
    # (private-eval cells may still be visible for display).
    if deployment_filter:
        matching = [
            c
            for c in support_cells
            if _deployment_matches(compute_meta.get(c["compute"], {}), deployment_filter)
        ]
        if not matching:
            pe_only = all(
                c.get("availability") == "private-eval"
                or c.get("lifecycle") in ("preview", "tech-preview")
                for c in support_cells
            )
            if not pe_only:
                return "deployment_excluded"

    eligible = [
        c
        for c in support_cells
        if not c.get("lifecycle_excluded") and not c.get("capability_excluded")
    ]
    if not eligible:
        if any(c.get("lifecycle_excluded") for c in support_cells):
            return "lifecycle_excluded"
        return "supported"

    if any(
        c.get("rank") is not None
        and c.get("recommendation") in ("PREFERRED", "RECOMMENDED")
        for c in eligible
    ):
        return "recommended"
    if any(
        c.get("recommendation") in ("PREFERRED", "RECOMMENDED", "ACCEPTABLE")
        or c.get("rank") is not None
        for c in eligible
    ):
        return "suitable"
    return "supported"


def _deployment_matches(compute: dict[str, Any], deployment: str) -> bool:
    dep = compute.get("deployment_class") or []
    if deployment in dep:
        return True
    if deployment == "enterprise" and (
        "datacenter" in dep or "enterprise-server" in dep
    ):
        return True
    if deployment == "datacenter" and "enterprise" in dep:
        return True
    if deployment in ("workstation", "local", "edge") and any(
        x in dep
        for x in ("workstation", "local", "edge", "departmental", "developer")
    ):
        return True
    return False


def best_rank(cells: dict[str, Any]) -> int:
    ranks = [c.get("rank") for c in cells.values() if c and c.get("rank") is not None]
    return min(ranks) if ranks else 9999


def order_portfolio_rows(
    models: list[str],
    row_status: dict[str, str],
    cells: dict[str, dict[str, Any]],
) -> list[str]:
    """Ranked suitable first, then suitable, supported, lifecycle, metadata, …"""
    return sorted(
        models,
        key=lambda m: (
            _STATUS_ORDER.get(row_status.get(m, "supported"), 50),
            best_rank(cells.get(m, {})),
            m,
        ),
    )


def normalize_show(show: str | None) -> str:
    s = (show or "all").lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "all-aims": "all",
        "all-eligible": "all",
        "recommended-only": "recommended",
        "recommended+supported": "suitable",
        "recommended-supported": "suitable",
        "deployed-only": "deployed",
        "preview": "preview-tp",
        "tech-preview": "preview-tp",
        "preview/tp": "preview-tp",
        "tp": "preview-tp",
    }
    return aliases.get(s, s)


def filter_display_rows(
    ordered_rows: list[str],
    *,
    row_status: dict[str, str],
    cells: dict[str, dict[str, Any]],
    show: str,
    search: str | None = None,
    vendor: str | None = None,
) -> list[str]:
    """Apply explicit Show / search / vendor filters only (no implicit top-N)."""
    show = normalize_show(show)
    out = list(ordered_rows)

    if vendor:
        v = vendor.lower()
        out = [m for m in out if vendor_of(m).lower() == v or v in m.lower()]

    if search:
        q = search.lower().strip()
        if q:
            out = [m for m in out if q in m.lower()]

    if show in ("all",):
        return out
    if show in ("recommended",):
        return [m for m in out if row_status.get(m) == "recommended"]
    if show in ("suitable",):
        return [
            m
            for m in out
            if row_status.get(m) in ("recommended", "suitable")
        ]
    if show in ("supported", "recommended+supported"):
        return [
            m
            for m in out
            if row_status.get(m) in ("recommended", "suitable", "supported")
        ]
    if show in ("deployed",):
        return [
            m
            for m in out
            if any((cells.get(m) or {}).get(c, {}).get("endpoint_available") for c in (cells.get(m) or {}))
        ]
    if show in ("preview-tp",):
        return [
            m
            for m in out
            if any(
                (cell or {}).get("lifecycle") in ("preview", "tech-preview")
                for cell in (cells.get(m) or {}).values()
            )
        ]
    # Unknown show → keep all (explicit filter failure should not truncate)
    return out


def executive_display_rows(
    ordered_rows: list[str],
    *,
    cells: dict[str, dict[str, Any]],
    row_status: dict[str, str],
    strategic_models: list[str] | None = None,
    limit: int = EXECUTIVE_TOP_ROWS,
) -> list[str]:
    """Truncate to top-ranked ∪ strategic ∪ private-eval ∪ deployed — labeled Executive."""
    selected: list[str] = []
    seen: set[str] = set()

    def add(m: str) -> None:
        if m in seen or m not in ordered_rows:
            return
        seen.add(m)
        selected.append(m)

    # Top-ranked by best cell rank
    by_rank = sorted(
        [m for m in ordered_rows if best_rank(cells.get(m, {})) < 9999],
        key=lambda m: best_rank(cells.get(m, {})),
    )
    for m in by_rank[:limit]:
        add(m)

    for m in strategic_models or []:
        add(m)

    for m in ordered_rows:
        cols = cells.get(m) or {}
        if any(
            (cols.get(f) or {}).get("lifecycle") in ("preview", "tech-preview")
            for f in PRIVATE_EVAL_COMPUTES
        ):
            add(m)
        if any((c or {}).get("endpoint_available") for c in cols.values()):
            add(m)
        if row_status.get(m) == "recommended" and m not in seen:
            add(m)

    # Preserve portfolio order among selected
    return [m for m in ordered_rows if m in seen]


def filter_columns(
    columns: list[str],
    compute_meta: dict[str, Any],
    compute_group: str | None,
) -> list[str]:
    group = (compute_group or "all").lower()
    if group in ("all", "", "none"):
        return list(columns)
    fam = {"instinct": "instinct", "epyc": "epyc", "radeon": "radeon"}.get(group)
    if not fam:
        return list(columns)
    return [c for c in columns if (compute_meta.get(c) or {}).get("family") == fam]


def why_not_recommended(
    model: str,
    *,
    row_status: str,
    cells: dict[str, Any],
    capability_why: str | None = None,
) -> list[str]:
    """Human-readable reasons a Portfolio row is not recommended."""
    if row_status == "recommended":
        return []
    reasons: list[str] = []
    if row_status == "metadata_incomplete":
        reasons.append("Model metadata incomplete in catalog/models.yaml")
    if row_status == "capability_excluded":
        reasons.append(capability_why or "Missing required capability for this use case")
    if row_status == "no_supported_compute":
        reasons.append("No AIM-supported compute cells in catalog")
    if row_status == "lifecycle_excluded":
        reasons.append("All AIM cells excluded by current lifecycle mode")
    if row_status == "deployment_excluded":
        reasons.append("AIM cells do not match deployment class filter")
    if row_status == "supported":
        reasons.append("AIM-supported but not preferred/recommended for this objective")
    if row_status == "suitable":
        reasons.append("Suitable (acceptable) but not top recommended for this objective")
    # Pull first exclusion / capability reason from cells
    for cell in cells.values():
        if not cell:
            continue
        if cell.get("exclusion_reason"):
            reasons.append(str(cell["exclusion_reason"]))
            break
        for r in cell.get("reasons") or []:
            if "capability_excluded" in str(r) or "excluded" in str(r).lower():
                reasons.append(str(r))
                break
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def catalog_counts(
    *,
    catalog_models: list[str],
    row_status: dict[str, str],
    cells: dict[str, dict[str, Any]],
    display_rows: list[str],
) -> dict[str, Any]:
    statuses = list(row_status.values())
    deployed = sum(
        1
        for m in catalog_models
        if any((cells.get(m) or {}).get(c, {}).get("endpoint_available") for c in (cells.get(m) or {}))
    )
    preview_tp = sum(
        1
        for m in catalog_models
        if any(
            (cell or {}).get("lifecycle") in ("preview", "tech-preview")
            for cell in (cells.get(m) or {}).values()
        )
    )
    return {
        "catalog_models": len(catalog_models),
        "rows": len(catalog_models),
        "display_rows": len(display_rows),
        "recommended": statuses.count("recommended"),
        "suitable": statuses.count("suitable") + statuses.count("recommended"),
        "supported": statuses.count("supported"),
        "capability_excluded": statuses.count("capability_excluded"),
        "lifecycle_excluded": statuses.count("lifecycle_excluded"),
        "deployment_excluded": statuses.count("deployment_excluded"),
        "no_supported_compute": statuses.count("no_supported_compute"),
        "metadata_incomplete": statuses.count("metadata_incomplete"),
        "deployed": deployed,
        "preview_tp": preview_tp,
        "coverage_complete": len(display_rows) >= len(catalog_models)
        or len(catalog_models) == 0,
    }


def compute_counts(
    columns: list[str],
    compute_meta: dict[str, Any],
) -> dict[str, Any]:
    by_family: dict[str, int] = {}
    for c in columns:
        fam = (compute_meta.get(c) or {}).get("family") or "unknown"
        by_family[fam] = by_family.get(fam, 0) + 1
    return {
        "columns": len(columns),
        "by_family": by_family,
        "ids": list(columns),
    }
