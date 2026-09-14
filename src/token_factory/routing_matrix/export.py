"""PowerPoint-ready Routing Matrix export (PNG / CSV / ZIP).

Consumes the same projection the Matrix UI shows via
``get_current_matrix_projection``. Does not change ranking, status, confidence,
or evidence — rendering/export only.

Styles:
- **executive** (Executive Slide) — 1920×1080 preferred-route + top-N table
- **full** — full projected grid canvas
- **slide** — accepted as an alias of **executive** (legacy)
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from token_factory.routing_matrix.executive import (
    ANTI_BENCHMARK,
    DEFAULT_TOP_N,
    build_executive_slide,
)
from token_factory.routing_matrix.projection import (
    MatrixProjection,
    cell_mark_text,
    get_current_matrix_projection,
    status_legend_names,
)


def _executive_csv_bytes(model: Any) -> bytes:
    """Lazy import so Streamlit hot-reload cannot bind a stale CSV writer."""
    from token_factory.routing_matrix.executive import executive_csv_bytes

    return executive_csv_bytes(model)


def _render_executive_png(model: Any, **kwargs: Any) -> bytes:
    from token_factory.routing_matrix.executive import render_executive_png

    return render_executive_png(model, **kwargs)

FormatName = Literal["png", "csv", "zip", "svg"]
StyleName = Literal["executive", "full", "slide"]
ScopeName = Literal["current", "all"]

CSV_FIELDS = (
    "use_case",
    "model",
    "compute",
    "row_status",
    "recommendation",
    "confidence",
    "evidence_badge",
    "evidence_confidence",
    "performance_evidence_status",
    "matrix_mark",
    "aim_support",
    "lifecycle",
    "rank",
    "score",
    "endpoint_available",
    "capability_excluded",
    "lifecycle_excluded",
)


@dataclass(frozen=True)
class ExportResult:
    """Bytes payload ready for ``st.download_button`` or disk write."""

    data: bytes
    filename: str
    mime: str
    format: str
    style: str
    scope: str
    note: str | None = None


def normalize_style(style: str) -> StyleName:
    """Map UI/CLI style names; ``slide`` → ``executive``."""
    key = (style or "executive").strip().lower()
    if key in ("slide", "executive", "executive-slide", "executive_slide"):
        return "executive"
    if key == "full":
        return "full"
    raise ValueError(f"Unsupported style: {style}")


def _sanitize_token(value: str | None, *, fallback: str = "na") -> str:
    text = (value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or fallback


def export_filename(
    *,
    use_case: str | None,
    lifecycle: str | None,
    view: str | None,
    style: str,
    fmt: str,
    scope: str = "current",
    timestamp: datetime | None = None,
) -> str:
    """Deterministic ``token-factory-routing-...`` sanitized name."""
    ts = timestamp or datetime.now(timezone.utc)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    style_token = normalize_style(style) if style else "executive"
    parts = [
        "token-factory-routing",
        "all-use-cases" if scope == "all" else _sanitize_token(use_case, fallback="matrix"),
        _sanitize_token(lifecycle, fallback="lifecycle"),
        _sanitize_token(view, fallback="view"),
        _sanitize_token(style_token, fallback="executive"),
        stamp,
    ]
    return "-".join(parts) + f".{fmt}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _perf_status(cell: dict[str, Any] | None) -> str:
    if not cell:
        return ""
    pe = cell.get("performance_evidence")
    if isinstance(pe, dict):
        return str(pe.get("status") or "")
    return ""


def projection_to_csv_rows(
    projection: MatrixProjection,
    *,
    include_use_case: bool = True,
) -> list[dict[str, Any]]:
    """Flatten projected cells to CSV row dicts (real fields only)."""
    rows: list[dict[str, Any]] = []
    for model in projection.rows:
        status = projection.row_status.get(model, "")
        for compute in projection.columns:
            cell = projection.cell(model, compute) or {}
            row = {
                "use_case": projection.use_case_id if include_use_case else "",
                "model": model,
                "compute": compute,
                "row_status": status,
                "recommendation": cell.get("recommendation"),
                "confidence": cell.get("confidence"),
                "evidence_badge": cell.get("evidence_badge"),
                "evidence_confidence": cell.get("evidence_confidence"),
                "performance_evidence_status": _perf_status(cell),
                "matrix_mark": cell.get("matrix_mark"),
                "aim_support": cell.get("aim_support"),
                "lifecycle": cell.get("lifecycle"),
                "rank": cell.get("rank"),
                "score": cell.get("score"),
                "endpoint_available": cell.get("endpoint_available"),
                "capability_excluded": cell.get("capability_excluded"),
                "lifecycle_excluded": cell.get("lifecycle_excluded"),
            }
            rows.append(row)
    return rows


def csv_bytes_from_rows(rows: Iterable[dict[str, Any]], *, include_use_case: bool) -> bytes:
    fields = list(CSV_FIELDS) if include_use_case else [f for f in CSV_FIELDS if f != "use_case"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fields})
    return buf.getvalue().encode("utf-8")


def projection_to_csv(projection: MatrixProjection, *, include_use_case: bool = False) -> bytes:
    rows = projection_to_csv_rows(projection, include_use_case=include_use_case)
    return csv_bytes_from_rows(rows, include_use_case=include_use_case)


def _title_lines(projection: MatrixProjection, style: str) -> tuple[str, str]:
    title = f"AMD Routing Matrix — {projection.use_case_name}"
    subtitle = (
        f"Lifecycle: {projection.lifecycle_mode or '—'} · "
        f"View: {projection.view_label or projection.view_mode} · "
        f"Objective: {projection.objective or '—'} · "
        f"Policy v{projection.policy_version or '—'} · "
        f"Style: {style}"
    )
    return title, subtitle


def _footer_text(projection: MatrixProjection, timestamp: datetime) -> str:
    stamp = timestamp.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Policy v{projection.policy_version or '—'} · {stamp} · {ANTI_BENCHMARK}"
    )


def _legend_text() -> str:
    statuses = " · ".join(status_legend_names())
    return (
        "Marks: ★ Preferred · ①–⑤ ranked · ✓ Acceptable · ○ Supported · "
        "◌ Capability mismatch · ⊘ Lifecycle-excluded · — No AIM support · "
        f"Row status: {statuses}"
    )


def _try_load_font(size: int):
    from PIL import ImageFont

    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_full_matrix_png(
    projection: MatrixProjection,
    *,
    timestamp: datetime | None = None,
) -> bytes:
    """Full Matrix canvas sized to the projected grid."""
    from PIL import Image, ImageDraw

    ts = timestamp or _utc_now()
    title, subtitle = _title_lines(projection, "full")
    footer = _footer_text(projection, ts)
    legend = _legend_text()

    n_rows = max(len(projection.rows), 1)
    n_cols = max(len(projection.columns), 1)

    model_w = 220
    col_w = max(72, min(120, 1400 // max(n_cols, 1)))
    row_h = 28
    header_block = 160
    pad = 28
    width = min(4800, max(1280, model_w + n_cols * col_w + 2 * pad))
    height = min(8000, max(720, header_block + n_rows * row_h + 80))
    title_size, sub_size, cell_size, footer_size = 26, 15, 12, 12

    img = Image.new("RGB", (width, height), "#0f0f0f")
    draw = ImageDraw.Draw(img)
    font_title = _try_load_font(title_size)
    font_sub = _try_load_font(sub_size)
    font_cell = _try_load_font(cell_size)
    font_footer = _try_load_font(footer_size)

    y = pad
    draw.text((pad, y), title, fill="#e8e8e8", font=font_title)
    y += title_size + 10
    draw.text((pad, y), subtitle, fill="#9a9a9a", font=font_sub)
    y += sub_size + 8
    draw.text((pad, y), legend, fill="#7a7a7a", font=font_footer)
    y += footer_size + 16

    table_top = y
    table_bottom = height - pad - footer_size - 16
    table_left = pad
    table_right = width - pad
    table_h = max(table_bottom - table_top, 40)
    table_w = max(table_right - table_left, 40)

    model_col_w = min(260, int(table_w * 0.2))
    col_w_f = (table_w - model_col_w) / n_cols
    header_h = max(28, int(table_h * 0.08))
    body_h = table_h - header_h
    row_h_f = body_h / n_rows

    draw.rectangle(
        [table_left, table_top, table_right, table_top + header_h],
        fill="#1a1a1a",
        outline="#333333",
    )
    draw.text(
        (table_left + 8, table_top + (header_h - cell_size) / 2),
        "MODEL / STATUS",
        fill="#888888",
        font=font_cell,
    )
    for i, col in enumerate(projection.columns):
        x = table_left + model_col_w + i * col_w_f
        label = col if len(col) <= 10 else col[:9] + "…"
        draw.text(
            (x + 4, table_top + (header_h - cell_size) / 2),
            label,
            fill="#999999",
            font=font_cell,
        )

    status_colors = {
        "recommended": "#8fd400",
        "suitable": "#dafd95",
        "supported": "#bbbbbb",
        "lifecycle_excluded": "#777777",
        "capability_excluded": "#888888",
        "deployment_excluded": "#777777",
        "metadata_incomplete": "#c08080",
        "no_supported_compute": "#555555",
    }

    for r_i, model in enumerate(projection.rows):
        y0 = table_top + header_h + r_i * row_h_f
        y1 = y0 + row_h_f
        bg = "#141414" if r_i % 2 == 0 else "#121212"
        draw.rectangle([table_left, y0, table_right, y1], fill=bg, outline="#2a2a2a")
        status = projection.row_status.get(model, "")
        short = model if len(model) < 34 else model[:31] + "…"
        draw.text((table_left + 6, y0 + 2), short, fill="#e8e8e8", font=font_cell)
        if row_h_f >= cell_size * 2 + 4:
            draw.text(
                (table_left + 6, y0 + 2 + cell_size + 1),
                status,
                fill=status_colors.get(status, "#666666"),
                font=font_footer,
            )
        for c_i, col in enumerate(projection.columns):
            cell = projection.cell(model, col)
            mark = cell_mark_text(cell)
            live = "●" if cell and cell.get("endpoint_available") else ""
            text = f"{mark}{live}"
            x = table_left + model_col_w + c_i * col_w_f
            color = "#8fd400" if mark == "★" else "#dafd95" if mark in "①②③④⑤" else "#cccccc"
            if mark in ("—", "⊘"):
                color = "#555555"
            elif mark in ("◌", "○"):
                color = "#888888"
            draw.text(
                (x + col_w_f / 2 - 4, y0 + max(2, (row_h_f - cell_size) / 2)),
                text,
                fill=color,
                font=font_cell,
            )

    draw.text((pad, height - pad - footer_size), footer, fill="#888888", font=font_footer)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def render_matrix_png(
    projection: MatrixProjection,
    *,
    style: StyleName | str = "executive",
    timestamp: datetime | None = None,
    top_n: int | None = DEFAULT_TOP_N,
    inventory_provided: bool | None = None,
) -> bytes:
    """PNG via Pillow — Executive Slide (16:9) or Full Matrix canvas."""
    style_key = normalize_style(style)
    ts = timestamp or _utc_now()
    if style_key == "executive":
        model = build_executive_slide(
            projection,
            top_n=top_n,
            timestamp=ts,
            inventory_provided=inventory_provided,
        )
        return _render_executive_png(model)
    return render_full_matrix_png(projection, timestamp=ts)


def render_matrix_svg(
    projection: MatrixProjection,
    *,
    style: StyleName | str = "executive",
    timestamp: datetime | None = None,
) -> bytes:
    """Optional lightweight SVG (same metadata/footer as PNG)."""
    style_key = normalize_style(style)
    ts = timestamp or _utc_now()
    title, subtitle = _title_lines(projection, style_key)
    footer = _footer_text(projection, ts)
    legend = _legend_text()
    width, height = (1920, 1080) if style_key == "executive" else (
        2400,
        max(900, 120 + 28 * len(projection.rows)),
    )

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0f0f0f"/>',
        f'<text x="36" y="48" fill="#e8e8e8" font-size="28" font-family="sans-serif">{esc(title)}</text>',
        f'<text x="36" y="76" fill="#9a9a9a" font-size="16" font-family="sans-serif">{esc(subtitle)}</text>',
        f'<text x="36" y="98" fill="#7a7a7a" font-size="12" font-family="sans-serif">{esc(legend)}</text>',
    ]
    y = 130
    lines.append(
        f'<text x="36" y="{y}" fill="#888" font-size="12" font-family="sans-serif">MODEL</text>'
    )
    x0 = 280
    col_w = max(60, (width - x0 - 36) / max(len(projection.columns), 1))
    for i, col in enumerate(projection.columns):
        lines.append(
            f'<text x="{x0 + i * col_w}" y="{y}" fill="#999" font-size="11" '
            f'font-family="sans-serif">{esc(col)}</text>'
        )
    y += 24
    for model in projection.rows:
        status = projection.row_status.get(model, "")
        short = model if len(model) < 36 else model[:33] + "…"
        lines.append(
            f'<text x="36" y="{y}" fill="#e8e8e8" font-size="12" font-family="monospace">'
            f"{esc(short)} ({esc(status)})</text>"
        )
        for i, col in enumerate(projection.columns):
            mark = cell_mark_text(projection.cell(model, col))
            lines.append(
                f'<text x="{x0 + i * col_w}" y="{y}" fill="#ccc" font-size="12" '
                f'font-family="sans-serif">{esc(mark)}</text>'
            )
        y += 22
        if y > height - 40:
            break
    lines.append(
        f'<text x="36" y="{height - 24}" fill="#888" font-size="13" font-family="sans-serif">'
        f"{esc(footer)}</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines).encode("utf-8")


def _matrix_kwargs_from_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    """Recover common ``engine.matrix`` kwargs echoed on the payload."""
    return {
        "objective": matrix.get("objective"),
        "deployment": matrix.get("deployment"),
        "utilization": matrix.get("utilization") or "medium",
        "show": matrix.get("show") or "all",
        "lifecycle_mode": matrix.get("lifecycle_mode"),
        "data_locality": bool(matrix.get("data_locality")),
        "serving_pattern": matrix.get("serving_pattern"),
        "latency_requirement": matrix.get("latency_requirement"),
        "view_mode": matrix.get("view_mode") or "portfolio",
        "search": matrix.get("search"),
        "vendor": matrix.get("vendor"),
        "compute_group": matrix.get("compute_group") or "all",
    }


def _csv_for_style(
    projection: MatrixProjection,
    *,
    style: StyleName,
    top_n: int | None,
    timestamp: datetime,
    inventory_provided: bool | None,
    include_use_case: bool,
) -> bytes:
    if style == "executive":
        model = build_executive_slide(
            projection,
            top_n=top_n,
            timestamp=timestamp,
            inventory_provided=inventory_provided,
        )
        return _executive_csv_bytes(model)
    return projection_to_csv(projection, include_use_case=include_use_case)


def export_routing_matrix(
    matrix: dict[str, Any] | MatrixProjection,
    *,
    format: FormatName = "csv",
    style: StyleName | str = "executive",
    timestamp: datetime | None = None,
    include_use_case: bool = False,
    top_n: int | None = DEFAULT_TOP_N,
    inventory_provided: bool | None = None,
) -> ExportResult:
    """Export the current-view projection (exact UI rows/cols / ranked top-N)."""
    ts = timestamp or _utc_now()
    projection = (
        matrix
        if isinstance(matrix, MatrixProjection)
        else get_current_matrix_projection(matrix)
    )
    style_key = normalize_style(style)
    fmt = format.lower()  # type: ignore[assignment]
    if fmt not in ("png", "csv", "zip", "svg"):
        raise ValueError(f"Unsupported format: {format}")

    inv = inventory_provided if inventory_provided is not None else projection.inventory_provided

    base_name = export_filename(
        use_case=projection.use_case_id,
        lifecycle=projection.lifecycle_mode,
        view=projection.view_mode,
        style=style_key,
        fmt=fmt if fmt != "zip" else "zip",
        scope="current",
        timestamp=ts,
    )

    if fmt == "csv":
        data = _csv_for_style(
            projection,
            style=style_key,
            top_n=top_n,
            timestamp=ts,
            inventory_provided=inv,
            include_use_case=include_use_case or style_key == "executive",
        )
        return ExportResult(
            data=data,
            filename=base_name,
            mime="text/csv",
            format="csv",
            style=style_key,
            scope="current",
        )
    if fmt == "png":
        data = render_matrix_png(
            projection,
            style=style_key,
            timestamp=ts,
            top_n=top_n,
            inventory_provided=inv,
        )
        return ExportResult(
            data=data,
            filename=base_name.replace(".zip", ".png") if base_name.endswith(".zip") else base_name,
            mime="image/png",
            format="png",
            style=style_key,
            scope="current",
        )
    if fmt == "svg":
        data = render_matrix_svg(projection, style=style_key, timestamp=ts)
        name = base_name if base_name.endswith(".svg") else export_filename(
            use_case=projection.use_case_id,
            lifecycle=projection.lifecycle_mode,
            view=projection.view_mode,
            style=style_key,
            fmt="svg",
            scope="current",
            timestamp=ts,
        )
        return ExportResult(
            data=data,
            filename=name,
            mime="image/svg+xml",
            format="svg",
            style=style_key,
            scope="current",
        )

    return _zip_single(
        projection,
        style=style_key,
        timestamp=ts,
        top_n=top_n,
        inventory_provided=inv,
    )


def _readme_text(
    *,
    scope: str,
    style: str,
    lifecycle: str | None,
    view: str | None,
    policy_version: str | None,
    use_cases: list[str],
    timestamp: datetime,
) -> str:
    stamp = timestamp.strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "Token Factory — Routing Matrix Export",
        "=====================================",
        "",
        f"Scope: {scope}",
        f"Style: {style}",
        f"Lifecycle: {lifecycle or '—'}",
        f"View: {view or '—'}",
        f"Policy version: {policy_version or '—'}",
        f"Generated: {stamp}",
        f"Note: {ANTI_BENCHMARK}",
        "",
        "Contents:",
        "- index.csv — manifest of included use cases / files",
        "- all-use-cases.csv — combined rows (style-dependent)",
        "- per use case PNG + CSV",
        "",
        "Use cases:",
        *[f"  - {uc}" for uc in use_cases],
        "",
        "Semantics are identical to the Streamlit AMD Routing Matrix projection.",
        "Statuses, confidence, and evidence are not upgraded for presentation.",
        "Runtime availability is shown separately from canonical ranking.",
        "",
    ]
    return "\n".join(lines)


def _zip_single(
    projection: MatrixProjection,
    *,
    style: StyleName,
    timestamp: datetime,
    top_n: int | None,
    inventory_provided: bool | None,
) -> ExportResult:
    buf = io.BytesIO()
    uc = _sanitize_token(projection.use_case_id, fallback="matrix")
    png_name = "executive.png" if style == "executive" else "matrix.png"
    csv_name = "executive.csv" if style == "executive" else "matrix.csv"
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            _readme_text(
                scope="current",
                style=style,
                lifecycle=projection.lifecycle_mode,
                view=projection.view_mode,
                policy_version=projection.policy_version,
                use_cases=[projection.use_case_id],
                timestamp=timestamp,
            ),
        )
        idx = io.StringIO()
        w = csv.DictWriter(idx, fieldnames=["use_case", "png", "csv", "rows", "columns"])
        w.writeheader()
        w.writerow(
            {
                "use_case": projection.use_case_id,
                "png": f"{uc}/{png_name}",
                "csv": f"{uc}/{csv_name}",
                "rows": (
                    (
                        len(projection.source.get("ranked") or [])
                        if top_n in (None, 0)
                        else min(top_n, len(projection.source.get("ranked") or []))
                    )
                    if style == "executive"
                    else len(projection.rows)
                ),
                "columns": len(projection.columns),
            }
        )
        zf.writestr("index.csv", idx.getvalue())
        csv_data = _csv_for_style(
            projection,
            style=style,
            top_n=top_n,
            timestamp=timestamp,
            inventory_provided=inventory_provided,
            include_use_case=True,
        )
        zf.writestr(f"{uc}/{csv_name}", csv_data)
        zf.writestr(
            f"{uc}/{png_name}",
            render_matrix_png(
                projection,
                style=style,
                timestamp=timestamp,
                top_n=top_n,
                inventory_provided=inventory_provided,
            ),
        )
        zf.writestr("all-use-cases.csv", csv_data)
    name = export_filename(
        use_case=projection.use_case_id,
        lifecycle=projection.lifecycle_mode,
        view=projection.view_mode,
        style=style,
        fmt="zip",
        scope="current",
        timestamp=timestamp,
    )
    return ExportResult(
        data=buf.getvalue(),
        filename=name,
        mime="application/zip",
        format="zip",
        style=style,
        scope="current",
    )


def export_all_use_cases(
    engine: Any,
    *,
    matrix_kwargs: dict[str, Any] | None = None,
    format: FormatName = "zip",
    style: StyleName | str = "executive",
    timestamp: datetime | None = None,
    endpoints: list[dict[str, Any]] | None = None,
    top_n: int | None = DEFAULT_TOP_N,
) -> ExportResult:
    """Iterate catalog use cases with the same lifecycle/objective/view filters.

    ``format=png`` (or svg) is coerced to a ZIP of per-use-case images — PNG is
    not a valid multi-use-case single-file format.
    """
    ts = timestamp or _utc_now()
    style_key = normalize_style(style)
    kwargs = dict(matrix_kwargs or {})
    kwargs.setdefault("view_mode", "portfolio")
    kwargs.setdefault("show", "all")
    if endpoints is not None:
        kwargs["endpoints"] = endpoints

    use_cases = [u["id"] for u in engine.list_use_cases()]
    projections: list[MatrixProjection] = []
    for uc_id in use_cases:
        matrix = engine.matrix(uc_id, **kwargs)
        projections.append(get_current_matrix_projection(matrix))

    fmt = format.lower()
    note = None
    if fmt in ("png", "svg"):
        note = f"All use cases + {fmt.upper()} exports as a ZIP of per-use-case {fmt.upper()} files."
        fmt = "zip"

    if fmt == "csv":
        if style_key == "executive":
            all_rows: list[dict[str, Any]] = []
            fields: list[str] = []
            for proj in projections:
                model = build_executive_slide(proj, top_n=top_n, timestamp=ts)
                text = _executive_csv_bytes(model).decode("utf-8")
                reader = csv.DictReader(io.StringIO(text))
                fields = list(reader.fieldnames or fields)
                all_rows.extend(list(reader))
            buf = io.StringIO()
            if not fields:
                from token_factory.routing_matrix.executive import EXECUTIVE_CSV_FIELDS

                fields = list(EXECUTIVE_CSV_FIELDS)
            writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for row in all_rows:
                writer.writerow(row)
            data = buf.getvalue().encode("utf-8")
        else:
            all_rows = []
            for proj in projections:
                all_rows.extend(projection_to_csv_rows(proj, include_use_case=True))
            data = csv_bytes_from_rows(all_rows, include_use_case=True)
        name = export_filename(
            use_case="all-use-cases",
            lifecycle=kwargs.get("lifecycle_mode"),
            view=kwargs.get("view_mode"),
            style=style_key,
            fmt="csv",
            scope="all",
            timestamp=ts,
        )
        return ExportResult(
            data=data,
            filename=name,
            mime="text/csv",
            format="csv",
            style=style_key,
            scope="all",
            note=note,
        )

    # ZIP bundle
    buf = io.BytesIO()
    lifecycle = kwargs.get("lifecycle_mode")
    view = kwargs.get("view_mode")
    policy_version = projections[0].policy_version if projections else None
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            _readme_text(
                scope="all",
                style=style_key,
                lifecycle=lifecycle,
                view=view,
                policy_version=policy_version,
                use_cases=use_cases,
                timestamp=ts,
            ),
        )
        idx = io.StringIO()
        w = csv.DictWriter(idx, fieldnames=["use_case", "png", "csv", "rows", "columns"])
        w.writeheader()
        combined_parts: list[bytes] = []
        for i, proj in enumerate(projections, start=1):
            uc = _sanitize_token(proj.use_case_id, fallback="matrix")
            if style_key == "executive":
                png_path = f"{i:02d}-{uc}-executive.png"
                csv_path = f"{i:02d}-{uc}-executive.csv"
            else:
                png_path = f"{uc}/matrix.png"
                csv_path = f"{uc}/matrix.csv"
            slide = build_executive_slide(proj, top_n=top_n, timestamp=ts)
            csv_data = (
                _executive_csv_bytes(slide)
                if style_key == "executive"
                else projection_to_csv(proj, include_use_case=True)
            )
            png_data = render_matrix_png(
                proj,
                style=style_key,
                timestamp=ts,
                top_n=top_n,
            )
            w.writerow(
                {
                    "use_case": proj.use_case_id,
                    "png": png_path,
                    "csv": csv_path,
                    "rows": len(slide.alternatives) if style_key == "executive" else len(proj.rows),
                    "columns": len(proj.columns),
                }
            )
            zf.writestr(csv_path, csv_data)
            zf.writestr(png_path, png_data)
            combined_parts.append(csv_data)
        zf.writestr("index.csv", idx.getvalue())
        # Combined CSV (re-header once)
        if style_key == "executive":
            all_rows = []
            fields: list[str] = []
            for part in combined_parts:
                reader = csv.DictReader(io.StringIO(part.decode("utf-8")))
                fields = list(reader.fieldnames or fields)
                all_rows.extend(list(reader))
            cbuf = io.StringIO()
            cw = csv.DictWriter(cbuf, fieldnames=fields or ["use_case"], extrasaction="ignore")
            cw.writeheader()
            for row in all_rows:
                cw.writerow(row)
            zf.writestr("all-use-cases.csv", cbuf.getvalue())
        else:
            all_rows = []
            for proj in projections:
                all_rows.extend(projection_to_csv_rows(proj, include_use_case=True))
            zf.writestr("all-use-cases.csv", csv_bytes_from_rows(all_rows, include_use_case=True))

    name = export_filename(
        use_case="all-use-cases",
        lifecycle=lifecycle,
        view=view,
        style=style_key,
        fmt="zip",
        scope="all",
        timestamp=ts,
    )
    return ExportResult(
        data=buf.getvalue(),
        filename=name,
        mime="application/zip",
        format="zip",
        style=style_key,
        scope="all",
        note=note,
    )


def resolve_export(
    *,
    engine: Any | None = None,
    matrix: dict[str, Any] | None = None,
    scope: ScopeName = "current",
    format: FormatName = "png",
    style: StyleName | str = "executive",
    matrix_kwargs: dict[str, Any] | None = None,
    endpoints: list[dict[str, Any]] | None = None,
    timestamp: datetime | None = None,
    top_n: int | None = DEFAULT_TOP_N,
) -> ExportResult:
    """UI-facing resolver: Current View vs All Use Cases + invalid combo handling."""
    style_key = normalize_style(style)
    if scope == "all":
        if engine is None:
            raise ValueError("engine is required for all-use-cases export")
        kwargs = matrix_kwargs or (_matrix_kwargs_from_matrix(matrix) if matrix else {})
        return export_all_use_cases(
            engine,
            matrix_kwargs=kwargs,
            format=format,
            style=style_key,
            timestamp=timestamp,
            endpoints=endpoints,
            top_n=top_n,
        )
    if matrix is None:
        raise ValueError("matrix is required for current-view export")
    return export_routing_matrix(
        matrix,
        format=format,
        style=style_key,
        timestamp=timestamp,
        top_n=top_n,
    )
