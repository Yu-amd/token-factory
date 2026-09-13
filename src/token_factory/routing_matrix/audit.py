"""Catalog / matrix audit — real counts; optional AMD docs reconcile note (no scrape)."""

from __future__ import annotations

from typing import Any

from token_factory.routing_matrix.loader import load_routing_bundle, normalize_model_id
from token_factory.routing_matrix.portfolio import (
    AMD_DOCS_MODELS_URL,
    catalog_model_ids,
    metadata_incomplete,
    vendor_of,
)

# Models observed on AMD docs models.html as of 2026-09-13 (manual reconcile; not scraped at runtime).
# Soft gap list only — do not invent AIM support matrices from this set.
AMD_DOCS_MODELS_SNAPSHOT_2026_09_13 = frozenset(
    {
        # Instinct
        "CohereLabs/command-a-reasoning-08-2025",
        "deepseek-ai/DeepSeek-R1",
        "deepseek-ai/DeepSeek-R1-0528",
        "deepseek-ai/DeepSeek-V3.1",
        "deepseek-ai/DeepSeek-V3.1-Terminus",
        "google/gemma-3-1b-it",
        "google/gemma-3-27b-it",
        "google/gemma-4-31B-it",
        "google/medgemma-27b-it",
        "meta-llama/Llama-3.1-405B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.2-1B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct",
        "MiniMaxAI/MiniMax-M2.5",
        "mistralai/Ministral-3-14B-Instruct-2512",
        "mistralai/Ministral-3-14B-Reasoning-2512",
        "mistralai/Mistral-Large-3-675B-Instruct-2512",
        "mistralai/Mistral-Small-24B-Instruct-2501",
        "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "Qwen/Qwen3-235B-A22B",
        "Qwen/Qwen3-32B",
        "Qwen/Qwen3-Coder-Next",
        "Qwen/Qwen3-VL-235B-A22B-Instruct",
        "Qwen/Qwen3-VL-235B-A22B-Thinking",
        "zai-org/GLM-4.7",
        # EPYC
        "google/gemma-4-E4B-it",
        "Qwen/Qwen3-30B-A3B",
        "Qwen/Qwen3-8B",
        "Qwen/Qwen3.5-4B",
        "Qwen/Qwen3.5-9B",
        "Qwen/Qwen3.6-35B-A3B",
        "unsloth/gpt-oss-20b-BF16",
        # Radeon
        "google/gemma-3n-E4B-it",
        "Qwen/Qwen3-VL-8B-Instruct",
        "zai-org/GLM-4.7-Flash",
    }
)


def audit_catalog(root: Any | None = None) -> dict[str, Any]:
    """Real merged-catalog counts + soft gaps vs a pinned AMD docs snapshot."""
    bundle = load_routing_bundle(root)
    aliases = bundle.get("aliases") or {}
    ga = [a["model"] for a in (bundle.get("aims_ga") or {}).get("aims") or []]
    merged = catalog_model_ids(bundle)
    models_meta = {m["model"] for m in (bundle.get("models") or {}).get("models") or []}
    compute = [c["id"] for c in (bundle.get("compute") or {}).get("compute") or []]

    tp_path_models = []
    tp_meta = (bundle.get("aims") or {}).get("tech_preview_metadata") or {}
    # Count unique TP-source models from merge tags
    for aim in (bundle.get("aims") or {}).get("aims") or []:
        cells = (aim.get("support") or {}).get("instinct") or {}
        mi = cells.get("MI350P")
        if isinstance(mi, dict) and mi.get("lifecycle") == "tech-preview":
            tp_path_models.append(aim["model"])

    incomplete = [
        m
        for m in merged
        if m not in models_meta
        or metadata_incomplete(
            type("E", (), {"models": {x["model"]: x for x in (bundle.get("models") or {}).get("models") or []}})(),
            m,
        )
    ]

    # Alias coverage
    alias_pairs = sorted(aliases.items())

    docs_snapshot = set(AMD_DOCS_MODELS_SNAPSHOT_2026_09_13)
    # Normalize docs ids through aliases for fair compare
    docs_canonical = {normalize_model_id(m, aliases) for m in docs_snapshot}
    in_catalog_not_docs = sorted(set(merged) - docs_canonical)
    in_docs_not_catalog = sorted(docs_canonical - set(merged))

    soft_gaps = []
    if in_docs_not_catalog:
        soft_gaps.append(
            {
                "kind": "docs_model_missing_from_catalog",
                "note": "Present on pinned AMD docs snapshot; not in local merged catalog "
                "(do not invent AIM×accel matrices without verification).",
                "models": in_docs_not_catalog,
            }
        )
    if in_catalog_not_docs:
        soft_gaps.append(
            {
                "kind": "catalog_model_not_on_docs_snapshot",
                "note": "In local catalog but absent from pinned docs models.html snapshot "
                "(may be Tech Preview, family-specific, or docs lag).",
                "models": in_catalog_not_docs,
            }
        )
    if incomplete:
        soft_gaps.append(
            {
                "kind": "metadata_incomplete",
                "note": "AIM model lacks usable capabilities in models.yaml",
                "models": incomplete,
            }
        )

    vendors: dict[str, int] = {}
    for m in merged:
        v = vendor_of(m)
        vendors[v] = vendors.get(v, 0) + 1

    return {
        "ga_aims": len(ga),
        "tech_preview_mi350p_models": len(sorted(set(tp_path_models))),
        "merged_catalog_models": len(merged),
        "models_yaml": len(models_meta),
        "compute_columns": len(compute),
        "compute_ids": compute,
        "aliases": len(aliases),
        "alias_pairs": [{"from": a, "to": b} for a, b in alias_pairs],
        "vendors": dict(sorted(vendors.items())),
        "merged_models": merged,
        "metadata_incomplete": incomplete,
        "amd_docs_url": AMD_DOCS_MODELS_URL,
        "amd_docs_reconcile": {
            "method": "pinned-snapshot",
            "runtime_scrape": False,
            "snapshot_label": "2026-09-13 models.html",
            "docs_snapshot_count": len(docs_canonical),
            "in_catalog_not_docs": in_catalog_not_docs,
            "in_docs_not_catalog": in_docs_not_catalog,
        },
        "soft_gaps": soft_gaps,
        "tech_preview_metadata": tp_meta,
    }


def audit_matrix(
    use_case_id: str = "coding-assistant",
    *,
    view_mode: str = "portfolio",
    root: Any | None = None,
    **matrix_kwargs: Any,
) -> dict[str, Any]:
    """Run Portfolio/Executive matrix and return coverage counts."""
    from token_factory.routing_matrix.engine import RecommendationEngine

    bundle = load_routing_bundle(root)
    engine = RecommendationEngine(bundle)
    matrix = engine.matrix(
        use_case_id,
        view_mode=view_mode,
        **matrix_kwargs,
    )
    catalog = audit_catalog(root)
    return {
        "use_case": use_case_id,
        "view_mode": matrix.get("view_mode"),
        "catalog_models": catalog["merged_catalog_models"],
        "rows": len(matrix.get("rows") or []),
        "display_rows": len(matrix.get("display_rows") or []),
        "columns": matrix.get("columns"),
        "catalog_counts": matrix.get("catalog_counts"),
        "compute_counts": matrix.get("compute_counts"),
        "coverage_warning": matrix.get("coverage_warning"),
        "row_status_counts": _count_statuses(matrix.get("row_status") or {}),
        "cells_with_aim_support": _count_aim_cells(matrix.get("cells") or {}),
        "cells_dash_no_support": _count_dash_cells(matrix.get("cells") or {}),
        "soft_gaps": catalog.get("soft_gaps"),
        "amd_docs_url": catalog.get("amd_docs_url"),
    }


def _count_statuses(row_status: dict[str, str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in row_status.values():
        out[s] = out.get(s, 0) + 1
    return dict(sorted(out.items()))


def _count_aim_cells(cells: dict[str, dict[str, Any]]) -> int:
    n = 0
    for cols in cells.values():
        for c in cols.values():
            if c and c.get("aim_support") is not None:
                n += 1
    return n


def _count_dash_cells(cells: dict[str, dict[str, Any]]) -> int:
    n = 0
    for cols in cells.values():
        for c in cols.values():
            if c and c.get("matrix_mark") == "—":
                n += 1
    return n
