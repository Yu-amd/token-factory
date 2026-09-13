# AIM Catalog

Token Factory’s **CAN RUN** authority for the Routing Matrix.

## Sources

| File | Role |
|------|------|
| `catalog/aims.yaml` | Authoritative **GA** AIM × accelerator support |
| `catalog/aims-tech-preview.yaml` | Additive **MI350P Tech Preview** cells (merged; never silent GA) |
| `catalog/model-aliases.yaml` | Spelling → canonical model id (no duplicate rows) |
| `catalog/models.yaml` | Capability / specialization metadata (for SHOULD RUN) |
| `catalog/compute.yaml` | Instinct / EPYC / Radeon column metadata |

Merge is performed by `token_factory.routing_matrix.loader.load_routing_bundle()`.
Canonical model ids after alias normalization form the **Portfolio Matrix** row universe.

## Portfolio vs ranking

- **Portfolio Matrix** rows = **all** merged catalog models (no silent top-N truncation).
- **Ranking / cards** remain selective: only capability-eligible, lifecycle-allowed cells are ranked.
- Unsuitable, lifecycle-excluded, and metadata-incomplete models stay **visible** in Portfolio with `row_status`.

## Cell marks

| Mark | Meaning |
|------|---------|
| `—` | **No AIM support** on that compute |
| `◌` | AIM support exists, but **capability mismatch** for the use case |
| `○` / `✓` / numbered / `★` | Supported / suitable / ranked (see routing matrix docs) |
| `⊘` | Lifecycle-excluded under current mode |

Capability mismatch must **not** be shown as `—`.

## Audit

```bash
token-factory catalog audit
token-factory matrix audit -u coding-assistant --view portfolio
```

`catalog audit` reports GA / Tech Preview / merged counts and optional soft gaps versus a
**pinned** snapshot of [AMD AIM models](https://enterprise-ai.docs.amd.com/en/latest/aims/catalog/models.html).
It does **not** scrape AMD docs at runtime and does **not** invent AIM×accelerator matrices.

## Soft gaps

When a model appears on AMD docs but local support matrices are unverified, record it in
audit soft gaps — do not fabricate Instinct/EPYC/Radeon cells.

## Related

- [AMD Routing Matrix](amd-routing-matrix.md)
- [Policy model](policy-model.md)
- [AMD compute guide](amd-compute-guide.md)
