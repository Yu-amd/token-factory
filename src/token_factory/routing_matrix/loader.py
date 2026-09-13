"""Load additive routing-matrix catalogs (does not replace aims.yaml GA authority)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from token_factory.catalog.loader import load_catalog
from token_factory.runtime.paths import repo_root

LIFECYCLES = ("ga", "preview", "tech-preview", "planned")
SUPPORT_LEVELS = ("optimized", "preview", "unoptimized", "general")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a mapping")
    return data


def catalog_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "catalog"


def normalize_model_id(model: str, aliases: dict[str, str] | None = None) -> str:
    """Map supplied spelling → canonical catalog id."""
    if aliases and model in aliases:
        return aliases[model]
    return model


def _parse_cell(
    raw: Any,
    *,
    default_lifecycle: str,
    family: str | None = None,
) -> tuple[str, str]:
    """Return (support_level, lifecycle) from string or mapping cell.

    Rules:
    - Explicit dict lifecycle always wins.
    - GA aims.yaml string cells on Instinct/EPYC → lifecycle=ga (support may still be preview).
    - Radeon + support=preview → lifecycle=preview (Radeon Preview AIMs).
    - Tech-preview merge file defaults to tech-preview.
    """
    if isinstance(raw, dict):
        support = str(raw.get("support") or raw.get("level") or "preview")
        lifecycle = str(raw.get("lifecycle") or default_lifecycle)
        return support, lifecycle
    support = str(raw)
    if default_lifecycle == "tech-preview":
        return support, "tech-preview"
    if family == "radeon" and support == "preview":
        return support, "preview"
    # Public GA catalog: support_level preview ≠ product lifecycle preview
    return support, default_lifecycle


def _merge_aim_cells(
    base_aims: list[dict[str, Any]],
    extra_aims: list[dict[str, Any]],
    *,
    default_lifecycle: str,
    source_tag: str,
) -> list[dict[str, Any]]:
    """Merge additive AIM cells into a deep copy of GA aims (by canonical model)."""
    by_model: dict[str, dict[str, Any]] = {}
    for aim in base_aims:
        entry = deepcopy(aim)
        # Normalize existing GA cells to {support, lifecycle}
        new_support: dict[str, dict[str, dict[str, str]]] = {}
        for family, mapping in (entry.get("support") or {}).items():
            if not isinstance(mapping, dict):
                continue
            new_support[family] = {}
            for accel, raw in mapping.items():
                support, lifecycle = _parse_cell(
                    raw, default_lifecycle="ga", family=family
                )
                new_support[family][accel] = {
                    "support": support,
                    "lifecycle": lifecycle,
                }
        entry["support"] = new_support
        entry.setdefault("lifecycle_source", "aims.yaml")
        by_model[entry["model"]] = entry

    for aim in extra_aims:
        model = aim["model"]
        entry = by_model.get(model)
        if entry is None:
            entry = {
                "model": model,
                "support": {},
                "lifecycle_source": source_tag,
                "provenance": aim.get("provenance"),
            }
            by_model[model] = entry
        for family, mapping in (aim.get("support") or {}).items():
            if not isinstance(mapping, dict):
                continue
            entry.setdefault("support", {}).setdefault(family, {})
            for accel, raw in mapping.items():
                support, lifecycle = _parse_cell(
                    raw, default_lifecycle=default_lifecycle, family=family
                )
                entry["support"][family][accel] = {
                    "support": support,
                    "lifecycle": lifecycle,
                    "source": source_tag,
                }
        if aim.get("provenance"):
            entry["tech_preview_provenance"] = aim["provenance"]

    return sorted(by_model.values(), key=lambda a: a["model"])


def load_routing_bundle(root: Path | None = None) -> dict[str, Any]:
    """Load aims (GA) + tech-preview merge + compute + use-cases + models + cost + policy."""
    base = catalog_dir(root)
    aims_ga = load_catalog(base / "aims.yaml")
    aliases_doc = (
        _load_yaml(base / "model-aliases.yaml")
        if (base / "model-aliases.yaml").exists()
        else {"aliases": {}}
    )
    aliases = dict(aliases_doc.get("aliases") or {})

    tp_path = base / "aims-tech-preview.yaml"
    tp_aims: list[dict[str, Any]] = []
    tp_meta: dict[str, Any] = {}
    if tp_path.exists():
        tp_doc = _load_yaml(tp_path)
        tp_meta = tp_doc.get("metadata") or {}
        for aim in tp_doc.get("aims") or []:
            canonical = normalize_model_id(aim["model"], aliases)
            merged = deepcopy(aim)
            merged["model"] = canonical
            # Preserve supplied source string
            prov = dict(merged.get("provenance") or {})
            prov.setdefault("source_string", aim["model"])
            merged["provenance"] = prov
            tp_aims.append(merged)

    merged_aims = _merge_aim_cells(
        list(aims_ga.get("aims") or []),
        tp_aims,
        default_lifecycle="tech-preview",
        source_tag="aims-tech-preview.yaml",
    )

    # Accel list: GA + MI350P
    accelerators = deepcopy(aims_ga.get("accelerators") or {})
    instinct = list(accelerators.get("instinct") or [])
    if "MI350P" not in instinct:
        # Insert after MI325X if present
        if "MI325X" in instinct:
            idx = instinct.index("MI325X") + 1
            instinct.insert(idx, "MI350P")
        else:
            instinct.append("MI350P")
        accelerators["instinct"] = instinct

    aims_merged = {
        **aims_ga,
        "accelerators": accelerators,
        "aims": merged_aims,
        "tech_preview_metadata": tp_meta,
        "aliases": aliases,
    }

    return {
        "aims": aims_merged,
        "aims_ga": aims_ga,  # pristine GA catalog for V1-style checks
        "compute": _load_yaml(base / "compute.yaml"),
        "use_cases": _load_yaml(base / "use-cases.yaml"),
        "models": _load_yaml(base / "models.yaml"),
        "cost_model": _load_yaml(base / "cost-model.yaml"),
        "policy": _load_yaml(base / "amd-routing-policy.yaml"),
        "aliases": aliases,
        "aliases_doc": aliases_doc,
    }


def mi350p_tech_preview_models(bundle: dict[str, Any] | None = None) -> list[str]:
    """Canonical MI350P Tech Preview model ids (exactly the normalized set)."""
    bundle = bundle or load_routing_bundle()
    models: list[str] = []
    for aim in bundle["aims"].get("aims") or []:
        cells = (aim.get("support") or {}).get("instinct") or {}
        cell = cells.get("MI350P")
        if isinstance(cell, dict) and cell.get("lifecycle") == "tech-preview":
            models.append(aim["model"])
    return sorted(set(models))
