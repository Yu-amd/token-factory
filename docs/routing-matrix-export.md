# Routing Matrix export (PowerPoint-ready)

Export the **AMD Routing Matrix** projection as PNG, CSV, or a ZIP bundle for
slides and reviews. Semantics match the Streamlit Matrix tab exactly.

**This is routing policy output — not a benchmark.** Statuses, confidence, and
evidence are never upgraded for presentation. **Executive Slide** is policy-first
(SHOULD RUN): canonical preferred and ranked alternatives only. Runtime inventory
(AVAILABLE NOW / escalation) belongs on Full Matrix, Simulate, and Automated Demo —
not the executive export.

## What is exported

Exports consume `RecommendationEngine.matrix(...)` then
`get_current_matrix_projection(matrix)` — the same rows/columns the UI shows.
Executive Slide additionally reads the canonical `ranked` list (all ranked by
default; optional Top N cap) without re-sorting.

| Scope | Behavior |
|-------|----------|
| **Current View** | Exact filtered `display_rows` × UI `display_cols` (Portfolio or Executive View), plus full ranked list (or Top N cap) for Executive Slide |
| **All Use Cases** | Iterates the catalog use-case list once each (canonical order), keeping the same lifecycle / objective / view / Show / compute-group filters |

| Layout | Behavior |
|--------|----------|
| **Executive Slide** (primary) | 1920-wide policy preferred-route callout + **all policy-ranked** alternatives by default (optional Top N 3/5/10), evidence strip — no runtime inventory / escalation; PNG height grows with row count |
| **Full Matrix** | Larger canvas sized to the projected grid |

Legacy style name `slide` aliases **Executive Slide**.

| Format | Behavior |
|--------|----------|
| **PNG** | Deterministic Pillow render |
| **CSV** | Executive = companion ranked rows shown on the slide; Full = all projected cells (`recommendation`, `confidence`, `evidence_*`, …) |
| **ZIP Bundle** | `README.txt`, `index.csv`, `all-use-cases.csv`, plus per-use-case PNG + CSV |
| **SVG** | Optional lightweight vector (same metadata) |

**Invalid combo:** All Use Cases + PNG → ZIP of per-use-case PNGs (UI shows a caption).

### Executive Slide zones

1. **Header** — Token Factory Routing Matrix · use-case display name · lifecycle · objective · Policy vX · Canonical policy  
2. **Preferred Route (policy)** — model, compute, 1–2 line canonical rationale; banner notes runtime inventory is not shown  
3. **Policy-ranked alternatives** — full ranked list by default (or Top N cap): Rank, Recommendation, Model, Compute, Lifecycle  
4. **Evidence strip** (no fabricated AMD MEASURED; confidence omitted from executive export)  
5. **Footer** — anti-benchmark · timestamp · policy version  

## File naming

Sanitized prefix:

```text
token-factory-routing-<use-case|all-use-cases>-<lifecycle>-<view>-<style>-<YYYYMMDDTHHMMSSZ>.<ext>
```

Example: `token-factory-routing-coding-assistant-production-executive-executive-20260913T200000Z.png`

All-use-cases Executive ZIP entries use numbered companions:

```text
01-coding-assistant-executive.png
01-coding-assistant-executive.csv
…
```

## UI

Streamlit **AMD Routing Matrix** → expander **Export for PowerPoint**:

1. Scope · Layout · Format (Top N optional when Executive Slide; default All ranked)
2. **Generate export**
3. `st.download_button` with bytes

Errors are caught and shown as warnings; they do not crash the tab.

## API

```python
from token_factory.routing_matrix import (
    RecommendationEngine,
    export_routing_matrix,
    export_all_use_cases,
    get_current_matrix_projection,
    resolve_export,
)

engine = RecommendationEngine()
matrix = engine.matrix("coding-assistant", view_mode="executive", lifecycle_mode="production")
proj = get_current_matrix_projection(matrix)  # exact UI grid
png = export_routing_matrix(matrix, format="png", style="executive")  # all ranked
png_cap = export_routing_matrix(matrix, format="png", style="executive", top_n=5)
bundle = export_all_use_cases(
    engine,
    matrix_kwargs={"lifecycle_mode": "production", "view_mode": "executive"},
    format="zip",
    style="executive",
)
```

Module: `src/token_factory/routing_matrix/export.py`  
Executive layout: `src/token_factory/routing_matrix/executive.py`  
Projection helper: `src/token_factory/routing_matrix/projection.py`

## Related

- [AMD Routing Matrix](amd-routing-matrix.md)
- [Policy model](policy-model.md)
- [Streamlit UI](ui.md)
