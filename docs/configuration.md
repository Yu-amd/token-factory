# Configuration

## Files

| File | Purpose |
|------|---------|
| `config/token-factory.yaml` | Cluster namespaces, component pins, paths |
| `config/endpoints.yaml` | Backend inventory (host, model, hardware) |
| `config/policies.yaml` | Active routing policy |
| `catalog/aims.yaml` | AMD AIM support matrix |

Copy examples:

```bash
cp config/token-factory.example.yaml config/token-factory.yaml
cp config/endpoints.example.yaml config/endpoints.yaml
cp config/policies.example.yaml config/policies.yaml
```

## Compile

```bash
token-factory compile
# outputs under generated/
```

## Validation

```bash
token-factory preflight
```

Schema enforced via JSON Schema in `src/token_factory/config/schema.py`.
