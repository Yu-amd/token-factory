"""AMD Opinionated Routing Matrix — recommendation engine."""

from __future__ import annotations

from token_factory.routing_matrix.engine import (
    RecommendationEngine,
    recommend,
    simulate_route,
)
from token_factory.routing_matrix.loader import (
    load_routing_bundle,
    mi350p_tech_preview_models,
    normalize_model_id,
)

__all__ = [
    "RecommendationEngine",
    "load_routing_bundle",
    "mi350p_tech_preview_models",
    "normalize_model_id",
    "recommend",
    "simulate_route",
]
