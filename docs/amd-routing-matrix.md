# AMD Opinionated Routing Matrix

Additive V2 feature on top of Token Factory V1. It does **not** replace Semantic Router,
Envoy AI Gateway, or the AIM support catalog. It answers a different question than V1 routing:

| Layer | Question | Source of truth |
|-------|----------|-----------------|
| **AIM Support** | CAN RUN? | `catalog/aims.yaml` (authoritative GA) + `catalog/aims-tech-preview.yaml` (MI350P TP merge) |
| **AMD Recommendation** | SHOULD RUN? | **`policies/amd-policy.yaml`** (canonical; v2.3) + scoring + **lifecycle filter** |
| **Runtime Availability** | AVAILABLE NOW? | `config/endpoints.yaml` (compiled inventory) |
| **Compiled Routes** | ACTIVE EXECUTION? | Profile overlay (`policies/profiles/amd-*.yaml`) → Semantic Router / AIGW |

Token economics (when used) only ranks **eligible** AIM-supported cells for a chosen objective.
There are **no fabricated $/token**, TTFT, or tokens/sec figures in this repository.

## Thesis

```text
AIM support        = CAN RUN
AMD canonical policy = SHOULD RUN
Live inventory     = AVAILABLE NOW
Compiled routes    = ACTIVE EXECUTION
Lifecycle          = GA vs Preview vs Tech Preview (orthogonal to support_level)
```

See [policy-model.md](policy-model.md) for the Policies tab / CLI / overlay model. The Routing Matrix is a **projection** of the same canonical policy.

## Catalogs

| File | Role |
|------|------|
| `catalog/aims.yaml` | GA AIM model × accelerator support (CAN RUN). Default lifecycle=`ga`. |
| `catalog/aims-tech-preview.yaml` | Additive MI350P Tech Preview cells (merged by loader; not silent GA). |
| `catalog/model-aliases.yaml` | Spelling normalization (no duplicate models). |
| `catalog/compute.yaml` | Instinct (incl. **MI350P**), EPYC, Radeon metadata |
| `catalog/use-cases.yaml` | Workloads, objectives, lifecycle modes, capability floors |
| `catalog/models.yaml` | Capability / specialization metadata |
| `catalog/cost-model.yaml` | Relative cost + empty measured benchmark schema |
| `catalog/amd-routing-policy.yaml` | Compat shim → `policies/amd-policy.yaml` |
| **`policies/amd-policy.yaml`** | **Canonical SHOULD RUN policy** (eligibility, positioning, objectives, overrides) |
| `policies/profiles/amd-*.yaml` | Profile overlays (objective / lifecycle / V1 SR routes) — not independent matrices |

Engine: `src/token_factory/routing_matrix/` (`RecommendationEngine`).

## Lifecycle (orthogonal to support_level)

| Lifecycle | Meaning | Default production |
|-----------|---------|--------------------|
| `ga` | Public GA AIM catalog | Allowed |
| `preview` | Product preview (e.g. **Radeon Preview** AIMs on R9700/W7900) | Excluded |
| `tech-preview` | Evaluation / release-planning (e.g. **MI350P**) | Excluded |
| `planned` | Future | Excluded |

Support levels remain `optimized|preview|unoptimized|general` and are **not** the same field.
Instinct/EPYC cells in `aims.yaml` with support=`preview` still have lifecycle=`ga` (GA catalog authority).
Radeon cells with support=`preview` infer lifecycle=`preview`.

UI / CLI lifecycle modes: **Production** | **Production + Preview** | **Tech Preview / Evaluation** | **All**.

## MI350P Tech Preview

- First-class compute: PCIe / OEM / enterprise-server — **not** an alias of MI350X.
- Positioning: between Radeon/EPYC workstation and rack-scale Instinct.
- 11 Tech Preview AIMs live in `aims-tech-preview.yaml` with `lifecycle: tech-preview`.
- Provenance: release-planning / tech-preview as_of ~2026-09-13 — **not** scraped from public GA AIM.
- Production / `amd-enterprise` defaults: `allow_tech_preview=false`.

### Alias normalization (supplied → canonical)

| Supplied | Canonical |
|----------|-----------|
| `openai/gpt-oss-120b` | `openai/gpt-oss-120b` |
| `meta-llama/Llama-3.3-70B-Instruct` | `meta-llama/Llama-3.3-70B-Instruct` |
| `mistralai/Mistral-Small-3.2-24B-Instruct-2501` | `mistralai/Mistral-Small-3.2-24B-Instruct-2506` |
| `google/gemma-3-27b-it` | `google/gemma-3-27b-it` |
| `Qwen/Qwen3.8-27B` | `Qwen/Qwen3.8-27B` |
| `google/gemma4-31b-it` | `google/gemma-4-31B-it` |
| `google/gemma4-26B-A4B` | `google/gemma4-26B-A4B` (distinct from `gemma-4-E4B-it`) |
| `google/gemma-4-12B-it` | `google/gemma-4-12B-it` |
| `openai/gpt-oss-20b` | `openai/gpt-oss-20b` |
| `Qwen/Qwen3.6-35B-A3B` | `Qwen/Qwen3.6-35B-A3B` |
| `Qwen/Qwen3.6-27B` | `Qwen/Qwen3.6-27B` |

## Radeon Preview AIMs

Stored in **GA** `catalog/aims.yaml` (already listed) with support=`preview`; loader tags lifecycle=`preview`.

| Model | R9700 | W7900 | Notes |
|-------|-------|-------|-------|
| `google/gemma-3n-E4B-it` | Preview | Preview | Vision / multimodal |
| `meta-llama/Llama-3.1-8B-Instruct` | Preview | Preview | Text-only |
| `Qwen/Qwen3-VL-8B-Instruct` | Preview | Preview | Vision / multimodal (local VLM) |
| `Qwen/Qwen3.5-9B` | Preview | Preview | Text-only |
| `zai-org/GLM-4.7-Flash` | Preview | Preview | Text-only |

Radeon is a **workstation / local / departmental / developer** class — not “cheaper Instinct.”
See [routing-economics.md](routing-economics.md) for locality, traffic, and escalation continuum.


## AMD Compute Positioning

### EPYC
EPYC is **CPU-centric / batch / low-QPS / fleet utilization** compute — **not** a GPU
interactive competitor. It rises for **batch / offline-batch** serving with
**relaxed / unconstrained** latency. It does **not** auto-rise for high-concurrency
interactive serving.

### Radeon
Radeon (R9700 / W7900) is **local / workstation / privacy** class. It can win when
the AIM is capable and locality is preferred. Incapable AIMs never win (e.g. text-only
for VLM). High-concurrency enterprise interactive prefers Instinct.

### MI350P
MI350P is **PCIe enterprise** Instinct — between workstation and rack-scale
(MI350X/MI355X). Tech Preview AIMs only; private-eval visibility preserved; never
silent production GA.

### Instinct rack (MI300X / MI350X / MI355X)
High-throughput / high-concurrency datacenter GPUs for interactive and online-throughput
workloads that need capability or concurrency beyond EPYC/Radeon/PCIe.

## Summary card selectors (distinct algorithms)

Cards do **not** relabel one global ranking:

| Card | Algorithm |
|------|-----------|
| **BEST PERFORMANCE** | Maximize capability + performance (+ AIM maturity / specialization); economics only as tie-break |
| **BEST BALANCE** | Trade capability / quality / perf / AIM / economic / deployment / traffic / lifecycle / serving / locality — may diverge when economics are materially better |
| **LOWEST-COST SUFFICIENT** | Constrained optimization: capability floor → filters → economically lowest among sufficient (never smallest=sufficient or cheapest-HW-without-floor) |
| **BEST BATCH** (optional) | When serving_pattern is batch/offline-batch |
| **BEST LOCAL** (optional) | When data locality / local deployment preferred |

## Serving Pattern

`Interactive` | `Online Throughput` | `Batch` | `Offline Batch`

- Interactive ≠ high traffic (traffic is a separate control)
- Batch ≠ high-concurrency interactive
- Latency requirement (`critical` / `important` / `relaxed` / `unconstrained`) is mapped
  from serving pattern + use-case overrides

## Matrix marks

User-facing cells number only the top ~3–5 candidates:
★ Preferred · ② ③ · ✓ Acceptable · ○ Supported · ◌ Capability mismatch (AIM exists) ·
⊘ Lifecycle-excluded · — **No AIM support** · ● Live.
Raw score and full rank stay in cell detail JSON.

In the Streamlit Matrix tab the mark legend and private-eval note sit **above** the
table (not below), so marks are readable before scrolling the grid.

## Portfolio Matrix vs Executive View

| Mode | Rows | Truncation |
|------|------|------------|
| **Portfolio Matrix** (default) | Full merged AIM catalog (`aims.yaml` ∪ tech-preview after aliases) | **None** silent. `display_rows` shrinks only via explicit Show / search / vendor filters. |
| **Executive View** | Same `rows` universe | May truncate `display_rows` to top-ranked ∪ strategic ∪ private-eval ∪ deployed; labeled + coverage warning. |

Payload fields:

- `rows` — full catalog model ids
- `display_rows` — after explicit filters / Executive truncation
- `row_status` — `recommended` \| `suitable` \| `supported` \| `capability_excluded` \| `lifecycle_excluded` \| `deployment_excluded` \| `no_supported_compute` \| `metadata_incomplete`
- `cells` — dense model × compute grid (`—` only when AIM support is absent)
- `catalog_counts` / `compute_counts` / `view_mode` / `coverage_warning`
- `why_not_recommended` — per-model reasons when not recommended

Compute columns include the full compute catalog (MI250X, EPYC_ZEN4/5, …) with UI group
toggle All \| Instinct \| EPYC \| Radeon. Focus columns are for ordering / Executive density only.

## Ranking

1. **Eligibility** — required capabilities; AIM cell must exist (GA or TP merge).
2. **Lifecycle filter** — production excludes preview + tech-preview by default.
3. **Base recommendation level** — AIM maturity + overrides; TP defaults to ACCEPTABLE.
4. **Unoptimized cap** — not promoted above `ACCEPTABLE` unless override says otherwise.
5. **Fit scores** — capability, performance, economic, deployment, lifecycle, serving_pattern, locality (not model-size ranking).
6. **Objective scoring** — includes **Lowest-Cost Sufficient**; traffic + serving pattern are material.
7. **Matrix marks** — number only top ~3–5; full rank in cell detail.
8. **Inventory overlay** — `endpoint_available`; does not invent support or change catalog semantics.

Levels: `PREFERRED` > `RECOMMENDED` > `ACCEPTABLE` > `SUPPORTED` > `NOT_SUPPORTED`.

## CLI

```bash
token-factory recommend --list-use-cases

# Production (excludes MI350P TP + Radeon Preview)
token-factory recommend -u coding-assistant -o balanced --lifecycle production

# Evaluation (allow tech-preview)
token-factory recommend -u coding-assistant -o balanced --lifecycle evaluation

# Lowest-Cost Sufficient
token-factory recommend -u simple-chat -o lowest-cost-sufficient -L production-preview

# Local / workstation + privacy
token-factory recommend -u simple-chat -o edge-local -L production-preview --data-locality

# I have MI350P / R9700
token-factory recommend --compute MI350P -u coding-assistant
token-factory recommend --compute R9700 -u simple-chat -o edge-local

token-factory recommend -u coding-assistant --simulate -L production

# Catalog / Portfolio coverage (real counts; no AMD docs scrape)
token-factory catalog audit
token-factory matrix audit -u coding-assistant --view portfolio
token-factory matrix audit -u coding-assistant --view executive
```

## UI

Streamlit tab **AMD Routing Matrix** (`make ui` → tab) **starts at the controls**
(no Matrix hero blurb). Deep policy narrative is on the **Policies** tab
([policy-model.md](policy-model.md) / `policies/amd-policy.yaml` v2.3).

- **View**: Portfolio Matrix (full catalog) \| Executive View (truncated)
- Controls: Use Case, Objective, Deployment, Lifecycle, Serving Pattern, Traffic, Data Locality, Show, Compute columns (All\|Instinct\|EPYC\|Radeon), Search, Vendor, I Have Compute
- Show: All AIMs \| Suitable \| Recommended \| Deployed \| Preview/TP
- Coverage strip: shown/catalog, suitable, recommended, deployed, preview/TP, exclusions
- Summary cards: distinct selectors — **BEST PERFORMANCE** \| **BEST BALANCE** \| **LOWEST-COST SUFFICIENT** (+ **BEST BATCH** / **BEST LOCAL** when relevant)
- Columns: full compute catalog by default (MI250X … MI355X · EPYC · Radeon); sticky header + sticky model column; internal scroll ~600px
- Rows: Portfolio = full catalog (ordered by row_status); Executive = truncated set with explicit label
- **Legend + private-eval note above the table**
- Cell tags: GA / Preview / Tech Preview; ◌ = capability mismatch (not `—`)
- Inspect any visible model/cell (not only ranked[:12]); **why not recommended** in detail
- Simulate route explains MI350P / Radeon lifecycle exclusions

## Related docs

- [AIM catalog](aim-catalog.md)
- [Routing economics](routing-economics.md)
- [Routing policies (V1)](routing-policy.md)
- [AIM / compute guide](amd-compute-guide.md)
- [Streamlit UI](ui.md)
- [Architecture](architecture.md)
