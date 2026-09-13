"""Config compilation pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from token_factory.compiler.ai_gateway import compile_ai_gateway_manifests
from token_factory.compiler.semantic_router import compile_semantic_router_values
from token_factory.compiler.ui_metadata import compile_ui_metadata
from token_factory.config.validator import validate_all
from token_factory.runtime.paths import generated_dir


def compile_all(
    endpoints: dict[str, Any],
    policies: dict[str, Any],
    token_factory: dict[str, Any],
    catalog: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    validate_all(endpoints, policies, token_factory, catalog)
    out = output_dir or generated_dir()
    out.mkdir(parents=True, exist_ok=True)

    sr_values = compile_semantic_router_values(endpoints, policies, token_factory)
    sr_path = out / "semantic-router-values.yaml"
    sr_path.write_text(yaml.safe_dump(sr_values, sort_keys=False), encoding="utf-8")

    manifests = compile_ai_gateway_manifests(endpoints, policies, token_factory)
    manifest_path = out / "ai-gateway-manifests.yaml"
    manifest_path.write_text(
        yaml.safe_dump_all(manifests, sort_keys=False),
        encoding="utf-8",
    )

    ui_meta = compile_ui_metadata(endpoints, policies, token_factory)
    ui_path = out / "ui-metadata.json"
    ui_path.write_text(json.dumps(ui_meta, indent=2), encoding="utf-8")

    return {
        "semantic_router_values": sr_path,
        "ai_gateway_manifests": manifest_path,
        "ui_metadata": ui_path,
    }
