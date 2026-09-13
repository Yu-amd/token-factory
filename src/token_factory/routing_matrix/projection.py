"""Shared Matrix display projection — same rows/cols the Streamlit UI shows.

Export and UI must call ``get_current_matrix_projection`` (or the column/row
helpers) on an ``engine.matrix(...)`` payload. Do not re-filter or re-rank.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from token_factory.routing_matrix.portfolio import FOCUS_COMPUTES, PRIVATE_EVAL_COMPUTES, ROW_STATUS


@dataclass(frozen=True)
class MatrixProjection:
    """Exact grid the Matrix UI renders for the current controls."""

    rows: list[str]
    columns: list[str]
    cells: dict[str, dict[str, Any]]
    row_status: dict[str, str]
    why_not_recommended: dict[str, list[str]]
    view_mode: str
    view_label: str
    use_case_id: str
    use_case_name: str
    objective: str | None
    lifecycle_mode: str | None
    serving_pattern: str | None
    policy_version: str | None
    show: str | None
    search: str | None
    vendor: str | None
    compute_group: str | None
    catalog_counts: dict[str, Any]
    coverage_warning: str | None
    source: dict[str, Any]

    def cell(self, model: str, compute: str) -> dict[str, Any] | None:
        return (self.cells.get(model) or {}).get(compute)


def display_columns(matrix: dict[str, Any]) -> list[str]:
    """Column ids shown in the UI for this matrix payload (Portfolio vs Executive)."""
    view_mode = matrix.get("view_mode") or "portfolio"
    if view_mode == "executive":
        focus_col_ids = tuple(matrix.get("focus_columns") or FOCUS_COMPUTES)
        display_cols = [c for c in (matrix.get("columns") or []) if c in focus_col_ids]
        columns_all = matrix.get("columns_all") or matrix.get("columns") or []
        for required in PRIVATE_EVAL_COMPUTES:
            if required not in display_cols and required in columns_all:
                display_cols.append(required)
        return display_cols
    return list(matrix.get("columns") or [])


def display_rows(matrix: dict[str, Any]) -> list[str]:
    """Row model ids shown in the UI (``display_rows``, else full ``rows``)."""
    row_models = list(matrix.get("display_rows") or [])
    if not row_models:
        row_models = list(matrix.get("rows") or [])
    return row_models


def get_current_matrix_projection(matrix: dict[str, Any]) -> MatrixProjection:
    """Project ``engine.matrix()`` into the exact rows/cols/cells the UI displays."""
    rows = display_rows(matrix)
    columns = display_columns(matrix)
    raw_cells = matrix.get("cells") or {}
    cells: dict[str, dict[str, Any]] = {}
    for model in rows:
        model_cells = raw_cells.get(model) or {}
        cells[model] = {col: model_cells.get(col) for col in columns}

    use_case = matrix.get("use_case") or {}
    if isinstance(use_case, dict):
        use_case_id = str(use_case.get("id") or "")
        use_case_name = str(use_case.get("display_name") or use_case_id)
    else:
        use_case_id = str(use_case)
        use_case_name = use_case_id

    return MatrixProjection(
        rows=rows,
        columns=columns,
        cells=cells,
        row_status=dict(matrix.get("row_status") or {}),
        why_not_recommended=dict(matrix.get("why_not_recommended") or {}),
        view_mode=str(matrix.get("view_mode") or "portfolio"),
        view_label=str(matrix.get("view_label") or matrix.get("view_mode") or "portfolio"),
        use_case_id=use_case_id,
        use_case_name=use_case_name,
        objective=matrix.get("objective"),
        lifecycle_mode=matrix.get("lifecycle_mode"),
        serving_pattern=matrix.get("serving_pattern"),
        policy_version=(
            str(matrix["policy_version"]) if matrix.get("policy_version") is not None else None
        ),
        show=matrix.get("show"),
        search=matrix.get("search"),
        vendor=matrix.get("vendor"),
        compute_group=matrix.get("compute_group"),
        catalog_counts=dict(matrix.get("catalog_counts") or {}),
        coverage_warning=matrix.get("coverage_warning"),
        source=matrix,
    )


def status_legend_names() -> list[str]:
    """Actual row-status names used by the engine/UI."""
    return list(ROW_STATUS)


def cell_mark_text(cell: dict[str, Any] | None) -> str:
    """Plain-text mark matching UI ``cell_label`` semantics (no HTML)."""
    if not cell:
        return "—"
    mark = cell.get("matrix_mark")
    if mark == "—" or (cell.get("aim_support") is None and mark in (None, "—")):
        return "—"
    if cell.get("capability_excluded"):
        return "◌"
    if cell.get("lifecycle_excluded"):
        pe = (
            cell.get("availability") == "private-eval"
            or cell.get("deployment_channel") == "private-eval-container"
            or cell.get("lifecycle") in ("preview", "tech-preview")
        )
        return "○" if pe else "⊘"
    if mark:
        return str(mark)
    rec = cell.get("recommendation", "SUPPORTED")
    if rec == "PREFERRED":
        return "★"
    if rec in ("RECOMMENDED", "ACCEPTABLE"):
        return "✓"
    return "○"
