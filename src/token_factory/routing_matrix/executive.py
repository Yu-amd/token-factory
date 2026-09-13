"""Executive Slide presentation model + PNG/CSV for Routing Matrix export.

Projection-only: consumes ranked cells from the same matrix payload the UI shows.
Does not re-rank, rewrite preferred, or upgrade confidence/evidence.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from token_factory.routing_matrix.projection import MatrixProjection

ANTI_BENCHMARK = "Routing policy output — not a benchmark"

TopN = Literal[3, 5, 10]
DEFAULT_TOP_N: TopN = 5

EXECUTIVE_CSV_FIELDS = (
    "rank",
    "recommendation",
    "model",
    "model_label",
    "compute",
    "lifecycle",
    "confidence",
    "runtime",
    "use_case",
    "evidence_badge",
    "performance_evidence_status",
)

_REC_LABEL = {
    "PREFERRED": "Preferred",
    "RECOMMENDED": "Recommended",
    "ACCEPTABLE": "Acceptable",
    "SUPPORTED": "Supported",
    "UNSUPPORTED": "Unsupported",
}

_OBJECTIVE_LABEL = {
    "balanced": "Balanced",
    "token-cost": "Lowest Token Cost",
    "lowest-cost-sufficient": "Lowest-Cost Sufficient",
    "quality": "Highest Quality",
    "latency": "Lowest Latency",
    "throughput": "Highest Throughput",
    "edge-local": "Local / Workstation First",
    "enterprise": "Enterprise Production",
    "batch": "Batch",
    "local": "Local",
}

_LIFECYCLE_MODE_LABEL = {
    "production": "Production",
    "production-preview": "Production + Preview",
    "evaluation": "Tech Preview / Evaluation",
    "all": "All",
}


def short_model_label(model: str | None) -> str:
    """Deterministic short label: strip org prefix ``Vendor/Name`` → ``Name``."""
    if not model:
        return "—"
    text = str(model).strip()
    if "/" in text:
        return text.rsplit("/", 1)[-1]
    return text


def recommendation_label(rec: str | None) -> str:
    if not rec:
        return "—"
    key = str(rec).strip().upper()
    if key in _REC_LABEL:
        return _REC_LABEL[key]
    if key == "LIFECYCLE_EXCLUDED" or "LIFECYCLE" in key and "EXCL" in key:
        return "Lifecycle Excluded"
    return str(rec).replace("_", " ").title()


def objective_label(objective: str | None) -> str:
    if not objective:
        return "—"
    return _OBJECTIVE_LABEL.get(str(objective), str(objective).replace("-", " ").title())


def lifecycle_mode_label(mode: str | None) -> str:
    if not mode:
        return "—"
    return _LIFECYCLE_MODE_LABEL.get(str(mode), str(mode).replace("-", " ").title())


def runtime_status_for_cell(
    cell: dict[str, Any] | None,
    *,
    inventory_provided: bool,
) -> str:
    """Runtime column value — never treats missing inventory as Unavailable."""
    if not inventory_provided:
        return "Not provided"
    if not cell:
        return "Unknown"
    if cell.get("endpoint_available"):
        return "Available"
    return "Not Deployed"


def _perf_status(cell: dict[str, Any] | None) -> str:
    if not cell:
        return ""
    pe = cell.get("performance_evidence")
    if isinstance(pe, dict):
        return str(pe.get("status") or "")
    return ""


def _canonical_rationale(cell: dict[str, Any] | None, *, max_parts: int = 3) -> str:
    """1–2 line rationale from engine reasons — no invented marketing copy."""
    if not cell:
        return "—"
    reasons = list(cell.get("reasons") or cell.get("why") or [])
    # Prefer concise strength-like reasons; skip noisy internal score chatter.
    skip = ("score=", "tie-breaker", "soft-penal")
    cleaned = [
        str(r).strip()
        for r in reasons
        if r and not any(s in str(r).lower() for s in skip)
    ]
    if not cleaned:
        cleaned = [str(r).strip() for r in reasons if r]
    parts = cleaned[:max_parts]
    if not parts:
        return "—"
    text = "; ".join(parts)
    if len(text) > 160:
        text = text[:157].rstrip() + "…"
    return text


def _confidence_caveat(cell: dict[str, Any] | None) -> str | None:
    if not cell:
        return None
    conf = str(cell.get("confidence") or "").strip()
    if conf.lower() == "high":
        return None
    uncertainties = []
    rationale = cell.get("rationale") or {}
    if isinstance(rationale, dict):
        uncertainties = [str(u) for u in (rationale.get("uncertainties") or []) if u]
    pe = cell.get("performance_evidence") or {}
    caveat = pe.get("caveat") if isinstance(pe, dict) else None
    if caveat and str(caveat) not in uncertainties:
        uncertainties.insert(0, str(caveat))
    # Dedupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for u in uncertainties:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    if uniq:
        return "; ".join(uniq[:2])
    if conf:
        return f"Confidence is {conf}; AMD comparative measurements may be pending"
    return None


def _evidence_strip_lines(cell: dict[str, Any] | None) -> list[str]:
    """Compact evidence lines from actual cell fields only."""
    if not cell:
        return ["Evidence: not available for preferred route"]
    pe = cell.get("performance_evidence") if isinstance(cell.get("performance_evidence"), dict) else {}
    status = str(pe.get("status") or "")
    badge = cell.get("evidence_badge") or pe.get("badge") or ""
    rationale = cell.get("rationale") if isinstance(cell.get("rationale"), dict) else {}
    evidence_bits = list(rationale.get("evidence") or [])

    lines = ["Evidence"]
    # Capability / docs
    cap = next((e for e in evidence_bits if "category=" in str(e)), None)
    if cap:
        lines.append(f"Capability / source: {str(cap).replace('category=', '')}")
    elif badge:
        lines.append(f"Evidence badge: {badge}")

    if status == "AMD_MEASURED":
        lines.append("AMD measured performance: Available")
    elif status == "PUBLIC_ONLY":
        lines.append("Public evaluation: Available")
        lines.append("AMD measured performance: Not yet available")
    elif status == "ESTIMATED":
        lines.append("AMD measured performance: Estimated only")
    elif status:
        lines.append(f"Performance evidence: {status}")
        if status != "AMD_MEASURED":
            lines.append("AMD measured performance: Not yet available")
    else:
        lines.append("AMD measured performance: Not yet available")

    return lines[:4]


@dataclass(frozen=True)
class ExecutiveRow:
    rank: int | None
    recommendation: str
    model: str
    model_label: str
    compute: str
    lifecycle: str
    confidence: str
    runtime: str
    evidence_badge: str
    performance_evidence_status: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class RuntimeEscalation:
    preferred_model: str
    preferred_compute: str
    selected_model: str
    selected_compute: str
    reason: str


@dataclass(frozen=True)
class ExecutiveSlideModel:
    """Slide-oriented view of canonical ranking (presentation only)."""

    use_case_id: str
    use_case_name: str
    lifecycle_mode: str | None
    lifecycle_label: str
    objective: str | None
    objective_label: str
    policy_version: str | None
    preferred: ExecutiveRow | None
    alternatives: list[ExecutiveRow]
    rationale: str
    evidence_lines: list[str]
    confidence_caveat: str | None
    inventory_provided: bool
    runtime_banner: str
    escalation: RuntimeEscalation | None
    top_n: int
    timestamp: datetime
    eligible_families: list[str] = field(default_factory=list)

    @property
    def footer(self) -> str:
        stamp = self.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"{ANTI_BENCHMARK}  ·  Generated {stamp}  ·  "
            f"Policy v{self.policy_version or '—'}"
        )


def ranked_candidates(projection: MatrixProjection) -> list[dict[str, Any]]:
    """Canonical ranked list from matrix payload (never re-sorted)."""
    ranked = list(projection.source.get("ranked") or [])
    if ranked:
        return ranked
    # Fallback: derive from cells by rank without changing order semantics
    cells: list[dict[str, Any]] = []
    for model in projection.rows:
        for compute in projection.columns:
            cell = projection.cell(model, compute)
            if not cell or cell.get("rank") is None:
                continue
            cells.append(cell)
    cells.sort(key=lambda c: (c.get("rank") is None, c.get("rank") or 10**9))
    return cells


def build_executive_slide(
    projection: MatrixProjection,
    *,
    top_n: int = DEFAULT_TOP_N,
    timestamp: datetime | None = None,
    inventory_provided: bool | None = None,
) -> ExecutiveSlideModel:
    """Build executive slide model from projection — no ranking changes."""
    if top_n not in (3, 5, 10):
        raise ValueError("top_n must be 3, 5, or 10")
    ts = timestamp or datetime.now(timezone.utc)
    inv = (
        bool(inventory_provided)
        if inventory_provided is not None
        else bool(projection.inventory_provided)
    )

    ranked = ranked_candidates(projection)
    top = ranked[:top_n]

    def _row(cell: dict[str, Any]) -> ExecutiveRow:
        model = str(cell.get("model") or "")
        return ExecutiveRow(
            rank=cell.get("rank"),
            recommendation=recommendation_label(cell.get("recommendation")),
            model=model,
            model_label=short_model_label(model),
            compute=str(cell.get("compute") or "—"),
            lifecycle=str(cell.get("lifecycle") or "—"),
            confidence=str(cell.get("confidence") or "—"),
            runtime=runtime_status_for_cell(cell, inventory_provided=inv),
            evidence_badge=str(cell.get("evidence_badge") or ""),
            performance_evidence_status=_perf_status(cell),
            raw=cell,
        )

    rows = [_row(c) for c in top]
    preferred_cell = top[0] if top else None
    preferred = rows[0] if rows else None

    escalation: RuntimeEscalation | None = None
    runtime_banner: str
    if not inv:
        runtime_banner = "Runtime availability: Not provided"
    elif preferred_cell and preferred_cell.get("endpoint_available"):
        runtime_banner = "Runtime Status: Available"
    elif preferred_cell:
        selected = next((c for c in ranked if c.get("endpoint_available")), None)
        if selected:
            escalation = RuntimeEscalation(
                preferred_model=short_model_label(preferred_cell.get("model")),
                preferred_compute=str(preferred_cell.get("compute") or "—"),
                selected_model=short_model_label(selected.get("model")),
                selected_compute=str(selected.get("compute") or "—"),
                reason="Preferred target not deployed",
            )
            runtime_banner = "Runtime Escalation"
        else:
            runtime_banner = "Runtime Status: Not Deployed"
    else:
        runtime_banner = "Runtime availability: Not provided" if not inv else "Runtime Status: Unknown"

    families: list[str] = []
    seen_f: set[str] = set()
    for c in ranked[:20]:
        fam = str(c.get("family") or "").strip()
        if fam and fam not in seen_f and fam != "unknown":
            seen_f.add(fam)
            families.append(fam.title() if fam.islower() else fam)

    return ExecutiveSlideModel(
        use_case_id=projection.use_case_id,
        use_case_name=projection.use_case_name or projection.use_case_id,
        lifecycle_mode=projection.lifecycle_mode,
        lifecycle_label=lifecycle_mode_label(projection.lifecycle_mode),
        objective=projection.objective,
        objective_label=objective_label(projection.objective),
        policy_version=projection.policy_version,
        preferred=preferred,
        alternatives=rows,
        rationale=_canonical_rationale(preferred_cell),
        evidence_lines=_evidence_strip_lines(preferred_cell),
        confidence_caveat=_confidence_caveat(preferred_cell),
        inventory_provided=inv,
        runtime_banner=runtime_banner,
        escalation=escalation,
        top_n=top_n,
        timestamp=ts,
        eligible_families=families[:4],
    )


def executive_csv_bytes(model: ExecutiveSlideModel) -> bytes:
    """Companion CSV: exact top-N rows shown on the slide."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(EXECUTIVE_CSV_FIELDS))
    writer.writeheader()
    for row in model.alternatives:
        writer.writerow(
            {
                "rank": row.rank if row.rank is not None else "",
                "recommendation": row.recommendation,
                "model": row.model,
                "model_label": row.model_label,
                "compute": row.compute,
                "lifecycle": row.lifecycle,
                "confidence": row.confidence,
                "runtime": row.runtime,
                "use_case": model.use_case_id,
                "evidence_badge": row.evidence_badge,
                "performance_evidence_status": row.performance_evidence_status,
            }
        )
    return buf.getvalue().encode("utf-8")


def _try_load_font(size: int):
    from PIL import ImageFont

    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _try_load_bold(size: int):
    from PIL import ImageFont

    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return _try_load_font(size)


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def render_executive_png(
    model: ExecutiveSlideModel,
    *,
    include_title: bool = True,
) -> bytes:
    """Render 1920×1080 executive slide PNG."""
    from PIL import Image, ImageDraw

    width, height = 1920, 1080
    margin_x, margin_y = 90, 70
    img = Image.new("RGB", (width, height), "#101010")
    draw = ImageDraw.Draw(img)

    font_brand = _try_load_bold(30)
    font_uc = _try_load_bold(26)
    font_meta = _try_load_font(16)
    font_section = _try_load_bold(15)
    font_pref_model = _try_load_bold(28)
    font_pref_meta = _try_load_font(18)
    font_body = _try_load_font(15)
    font_table_h = _try_load_bold(15)
    font_table = _try_load_font(14)
    font_footer = _try_load_font(12)
    font_small = _try_load_font(13)

    y = margin_y
    content_right = width - margin_x
    content_w = content_right - margin_x

    if include_title:
        draw.text((margin_x, y), "Token Factory Routing Matrix", fill="#c8c8c8", font=font_brand)
        y += 38
    draw.text((margin_x, y), model.use_case_name, fill="#f0f0f0", font=font_uc)
    y += 34
    meta = (
        f"{model.lifecycle_label}  ·  {model.objective_label}  ·  "
        f"Policy v{model.policy_version or '—'}"
    )
    draw.text((margin_x, y), meta, fill="#8a8a8a", font=font_meta)
    y += 28
    if model.eligible_families:
        draw.text(
            (margin_x, y),
            "Eligible compute estate: " + " · ".join(model.eligible_families),
            fill="#666666",
            font=font_small,
        )
        y += 22

    # Divider
    draw.line([(margin_x, y), (content_right, y)], fill="#2e2e2e", width=1)
    y += 18

    # Preferred Route callout (left) + optional Runtime Escalation (right)
    callout_top = y
    callout_h = 200
    left_w = int(content_w * 0.62) if model.escalation else content_w
    draw.rectangle(
        [margin_x, callout_top, margin_x + left_w, callout_top + callout_h],
        fill="#161616",
        outline="#333333",
    )
    cx, cy = margin_x + 24, callout_top + 18
    draw.text((cx, cy), "Preferred Route", fill="#8fd400", font=font_section)
    cy += 26
    if model.preferred:
        draw.text((cx, cy), model.preferred.model_label, fill="#ffffff", font=font_pref_model)
        cy += 34
        draw.text(
            (cx, cy),
            f"{model.preferred.compute}  ·  Confidence: {model.preferred.confidence}",
            fill="#b0b0b0",
            font=font_pref_meta,
        )
        cy += 28
        why_lines = _wrap_text(draw, f"Why: {model.rationale}", font_body, left_w - 48)
        for line in why_lines[:2]:
            draw.text((cx, cy), line, fill="#888888", font=font_body)
            cy += 20
        if not model.escalation:
            cy += 8
            draw.text((cx, cy), model.runtime_banner, fill="#9a9a9a", font=font_small)
    else:
        draw.text((cx, cy), "No ranked preferred route", fill="#888888", font=font_pref_meta)

    if model.escalation:
        esc = model.escalation
        rx0 = margin_x + left_w + 16
        draw.rectangle(
            [rx0, callout_top, content_right, callout_top + callout_h],
            fill="#1a1814",
            outline="#5a4a30",
        )
        ex, ey = rx0 + 20, callout_top + 18
        draw.text((ex, ey), "Runtime Escalation", fill="#c4a35a", font=font_section)
        ey += 28
        draw.text((ex, ey), "Canonical Preferred", fill="#777777", font=font_small)
        ey += 18
        draw.text(
            (ex, ey),
            f"{esc.preferred_model} × {esc.preferred_compute}",
            fill="#e8e8e8",
            font=font_body,
        )
        ey += 26
        draw.text((ex, ey), "Runtime Selected", fill="#777777", font=font_small)
        ey += 18
        draw.text(
            (ex, ey),
            f"{esc.selected_model} × {esc.selected_compute}",
            fill="#e8e8e8",
            font=font_body,
        )
        ey += 26
        draw.text((ex, ey), f"Reason: {esc.reason}", fill="#a09070", font=font_small)

    y = callout_top + callout_h + 22

    # Ranked alternatives table
    draw.text(
        (margin_x, y),
        f"Ranked alternatives (top {model.top_n})",
        fill="#8fd400",
        font=font_section,
    )
    y += 26

    headers = ["Rank", "Recommendation", "Model", "Compute", "Lifecycle", "Confidence", "Runtime"]
    col_w = [70, 160, 340, 140, 140, 140, 200]
    # stretch last columns to fill
    total_fixed = sum(col_w)
    if total_fixed < content_w:
        col_w[-1] += content_w - total_fixed

    row_h = 36
    header_h = 34
    table_top = y
    draw.rectangle(
        [margin_x, table_top, content_right, table_top + header_h],
        fill="#1a1a1a",
        outline="#333333",
    )
    x = margin_x + 10
    for h, w in zip(headers, col_w, strict=True):
        draw.text((x, table_top + 8), h, fill="#888888", font=font_table_h)
        x += w

    y = table_top + header_h
    for i, row in enumerate(model.alternatives):
        bg = "#141414" if i % 2 == 0 else "#121212"
        draw.rectangle([margin_x, y, content_right, y + row_h], fill=bg, outline="#2a2a2a")
        vals = [
            str(row.rank if row.rank is not None else "—"),
            row.recommendation,
            row.model_label if len(row.model_label) <= 36 else row.model_label[:33] + "…",
            row.compute,
            row.lifecycle,
            row.confidence,
            row.runtime,
        ]
        x = margin_x + 10
        for col_i, (v, w) in enumerate(zip(vals, col_w, strict=True)):
            color = "#8fd400" if col_i == 1 and v == "Preferred" else "#d8d8d8"
            draw.text((x, y + 9), v, fill=color, font=font_table)
            x += w
        y += row_h

    y += 20
    # Evidence strip
    strip_h = 118 if model.confidence_caveat else 92
    draw.rectangle(
        [margin_x, y, content_right, y + strip_h],
        fill="#141414",
        outline="#2e2e2e",
    )
    ey = y + 12
    for line in model.evidence_lines:
        draw.text((margin_x + 16, ey), line, fill="#9a9a9a", font=font_small)
        ey += 18
    if model.confidence_caveat and model.preferred:
        draw.text(
            (margin_x + 16, ey + 4),
            f"Confidence: {model.preferred.confidence} — {model.confidence_caveat}",
            fill="#c4a35a",
            font=font_small,
        )

    # Footer
    draw.text(
        (margin_x, height - margin_y - 14),
        model.footer,
        fill="#777777",
        font=font_footer,
    )

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
