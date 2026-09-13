# Test Environment (Discoveries)

Draft notes from public endpoint discovery — **not** used as install foundation.

## Public HTTP backends (reference)

| Host | Port | Model | Role |
|------|------|-------|------|
| 129.212.183.201 | 8000 | openai/gpt-oss-120b | coding |
| 165.245.136.245 | 8000 | openai/gpt-oss-20b | general |
| 165.245.133.102 | 8080 | (legacy SR/gateway demo) | avoid |

Token Factory builds a **clean** stack on local kind; do not reuse 165.245.133.102.

## Local validation

```bash
pip install -e ".[dev,mock]"
make test
make demo          # mock OpenAI server on :8000
curl localhost:8000/v1/models
```

## CI

GitHub Actions: lint, unit tests, config compile, Helm template dashboard verification.
