# Routing Matrix export (PowerPoint-ready)

Export the **AMD Routing Matrix** projection as PNG, CSV, or a ZIP bundle for
slides and reviews. Semantics match the Streamlit Matrix tab exactly.

**This is routing policy output — not a benchmark.** Statuses, confidence, and
evidence are never upgraded for presentation.

## What is exported

Exports consume `RecommendationEngine.matrix(...)` then
`get_current_matrix_projection(matrix)` — the same rows/columns the UI shows:

| Scope | Behavior |
|-------|----------|
| **Current View** | Exact filtered `display_rows` × UI `display_cols` (Portfolio or Executive) |
| **All Use Cases** | Iterates the catalog use-case list once each, keeping the same lifecycle / objective / view / Show / compute-group filters |

| Style | Behavior |
|-------|----------|
| **Slide** | 16:9 ≈ 1920×1080, concise layout for decks |
| **Full Matrix** | Larger canvas sized to the projected grid |

| Format | Behavior |
|--------|----------|
| **PNG** | Deterministic Pillow render (title, legend with real status names, footer) |
| **CSV** | Real cell fields only (`recommendation`, `confidence`, `evidence_*`, `matrix_mark`, …) |
| **ZIP Bundle** | `README.txt`, `index.csv`, `all-use-cases.csv`, plus per-use-case `matrix.png` + `matrix.csv` |
| **SVG** | Optional lightweight vector (same metadata) |

**Invalid combo:** All Use Cases + PNG → ZIP of per-use-case PNGs (UI shows a caption).

## Footer / title

- Title: use case display name
- Subtitle: lifecycle, view, objective, policy version, style
- Legend: matrix marks + actual `row_status` names
- Footer: dynamic policy version, UTC timestamp, *Routing policy output — not a benchmark*

## File naming

Sanitized prefix:

```text
token-factory-routing-<use-case|all-use-cases>-<lifecycle>-<view>-<style>-<YYYYMMDDTHHMMSSZ>.<ext>
```

Example: `token-factory-routing-coding-assistant-production-executive-slide-20260913T200000Z.png`

## UI

Streamlit **AMD Routing Matrix** → expander **Export for PowerPoint**:

1. Scope · Style · Format
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
png = export_routing_matrix(matrix, format="png", style="slide")
bundle = export_all_use_cases(
    engine,
    matrix_kwargs={"lifecycle_mode": "production", "view_mode": "executive"},
    format="zip",
    style="slide",
)
```

Module: `src/token_factory/routing_matrix/export.py`  
Projection helper: `src/token_factory/routing_matrix/projection.py`

## Related

- [AMD Routing Matrix](amd-routing-matrix.md)
- [Policy model](policy-model.md)
- [Streamlit UI](ui.md)
