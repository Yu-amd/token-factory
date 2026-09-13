"""Version and pinned component matrix."""

from pathlib import Path

__version__ = "0.1.0"

# Pinned to Semantic Router upstream e2e (EG v1.6.0 + AIGW v0.4.0 + SR chart 0.3.0).
PINNED_VERSIONS = {
    "semantic_router_chart": "0.3.0",
    "semantic_router_app": "v0.3.0",
    "envoy_ai_gateway": "v0.4.0",
    "envoy_gateway": "v1.6.0",
    "envoy_gateway_crds": "v1.6.0",
    "prometheus": "v2.55.1",
    "grafana": "11.4.0",
}

VIRTUAL_MODEL = "token-factory/auto"

NAMESPACES = {
    "token_factory": "token-factory",
    "envoy_gateway": "envoy-gateway-system",
    "envoy_ai_gateway": "envoy-ai-gateway-system",
    "semantic_router": "vllm-semantic-router-system",
    "observability": "observability",
}


def read_version_file() -> str:
    root = Path(__file__).resolve().parents[2]
    version_file = root / "VERSION"
    if version_file.exists():
        first_line = version_file.read_text(encoding="utf-8").splitlines()[0].strip()
        if first_line and not first_line.startswith("#"):
            return first_line
    return __version__
