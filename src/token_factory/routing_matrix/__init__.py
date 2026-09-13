"""AMD Opinionated Routing Matrix — recommendation engine."""

from __future__ import annotations

from token_factory.routing_matrix.audit import audit_catalog, audit_matrix
from token_factory.routing_matrix.engine import (
    RecommendationEngine,
    recommend,
    simulate_route,
)
from token_factory.routing_matrix.export import (
    export_all_use_cases,
    export_routing_matrix,
    resolve_export,
)
from token_factory.routing_matrix.loader import (
    load_routing_bundle,
    mi350p_tech_preview_models,
    normalize_model_id,
)
from token_factory.routing_matrix.projection import (
    get_current_matrix_projection,
)

__all__ = [
    "RecommendationEngine",
    "audit_catalog",
    "audit_matrix",
    "export_all_use_cases",
    "export_routing_matrix",
    "get_current_matrix_projection",
    "load_routing_bundle",
    "mi350p_tech_preview_models",
    "normalize_model_id",
    "recommend",
    "resolve_export",
    "simulate_route",
]
