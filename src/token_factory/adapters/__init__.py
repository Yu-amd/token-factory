"""Pluggable OSS-first adapters for Token Factory execution plane.

Token Factory owns AMD opinionated policy. Gateways/routers/peers are swappable.
"""

from __future__ import annotations

from token_factory.adapters.registry import AdapterBundle, resolve_adapters

__all__ = ["AdapterBundle", "resolve_adapters"]
