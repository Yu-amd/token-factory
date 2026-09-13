"""Automated Demo — routing-policy and observability validation.

This package validates that Token Factory classifies workloads, applies AMD
canonical routing policy, selects eligible model × compute endpoints, exercises
fallback, and emits telemetry. It is not a benchmark framework.
"""

from token_factory.demo.loader import list_packs, load_pack, scenarios_dir
from token_factory.demo.models import DemoRequest, DemoRun, ValidationStatus
from token_factory.demo.runner import DemoRunner, run_demo

__all__ = [
    "DemoRequest",
    "DemoRun",
    "DemoRunner",
    "ValidationStatus",
    "list_packs",
    "load_pack",
    "run_demo",
    "scenarios_dir",
]
