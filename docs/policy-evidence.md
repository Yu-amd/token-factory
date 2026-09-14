# Policy evidence governance

> **Token Factory recommendations are policy decisions derived from model capability, AMD AIM support, deployment requirements, lifecycle, economics, and available performance evidence. Missing evidence lowers recommendation confidence and should not be interpreted as proof of inferiority.**

Token Factory is **not** a benchmark portal. Evidence influences AMD routing policy confidence; it does not produce leaderboards or fabricated $/token or AMD performance numbers.

## How capabilities are determined

1. Official model card / provider documentation (preferred)
2. Official technical report
3. AMD AIM documentation
4. Reputable published evaluation (provenance pointer; values optional)
5. Conservative inference from model id (fallback only — weak hint)

Capabilities use a **tri-state**: `true` | `false` | `unknown`.

- `unknown` ≠ `false`
- Unknown required capabilities mark **metadata-incomplete** and degrade confidence; they are not hard excludes unless policy mode says so (production excludes unknown; evaluation may admit)

## Workload strengths

Coarse `specialization: coding` is retained only as a **weak hint**. Qualitative strengths drive `quality_fit`:

- `code_completion`, `code_generation`, `code_review`
- `repository_reasoning`, `agentic_coding`, `terminal_tasks`
- `general_reasoning`, `long_context`

Values: `unknown` | `low` | `medium` | `high` | `very-high` — policy inputs, not scores.

## Evidence catalog

Structured records live in [`catalog/evidence.yaml`](../catalog/evidence.yaml):

| Field | Role |
|-------|------|
| id, model, workload, metric | Identity |
| value | Optional — **never** without provenance |
| source, source_type, date, methodology | Provenance |
| confidence | VERIFIED / PUBLIC_EVAL / MODEL_CARD / AMD_MEASURED / AMD_ESTIMATED / INFERRED / UNKNOWN |
| notes | Human context |

`amd_measurements` may be `null` until first-party AMD data is ingested. Cost evidence uses RELATIVE / UNKNOWN without inventing $/token.

## Evidence maturity (E0–E4)

| Level | Meaning |
|-------|---------|
| E0 | Unknown |
| E1 | Inferred |
| E2 | Official model documentation |
| E3 | Public validated evaluation |
| E4 | AMD measured |

## Recommendation confidence

| Level | Typical conditions |
|-------|--------------------|
| **High** | Optimized AIM + GA + capability verified + **AMD_MEASURED** (or multiple verified sources including measured) |
| **Medium** | Strong model-card / public evidence + mature AIM; AMD comparative pending |
| **Low** | Inferred capability / limited task evidence / no AMD performance data |
| **Experimental** | Preview / Tech Preview / incomplete metadata |

**Preferred without AMD measured evidence cannot be High.**

## Ranking dimensions

Staged eligibility, then rank within the eligible set:

1. capability_fit  
2. quality_fit  
3. performance_fit  
4. economic_fit  
5. deployment_fit  
6. lifecycle_fit  
7. serving_pattern_fit  
8. locality_fit  
9. evidence_confidence  

`INSTINCT_GEN_BIAS` and specialization / “Coder” name heuristics are **tie-breakers only** unless AMD measured evidence supports a stronger preference.

## Override governance

Explicit policy overrides expose auditable fields:

`decision`, `rationale`, `owner`, `reviewed`, `expires`

Overrides encode AMD policy preferences — not benchmark “wins.”

## CLI

```bash
token-factory evidence audit
token-factory evidence gaps
token-factory policy audit
token-factory policy compare \
  --use-case coding-assistant \
  --model-a Qwen/Qwen3-Coder-Next \
  --model-b zai-org/GLM-4.7 \
  --compute MI355X
```

## Related

- [policy-model.md](policy-model.md) — four-layer CAN/SHOULD/AVAILABLE/ACTIVE model  
- [amd-routing-matrix.md](amd-routing-matrix.md) — matrix UX and catalogs  
- [routing-economics.md](routing-economics.md) — relative cost evidence  
