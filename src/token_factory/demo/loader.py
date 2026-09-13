"""Load declarative Automated Demo scenario packs from demo/scenarios/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from token_factory.demo.schema import ScenarioSchemaError, assert_valid_pack
from token_factory.runtime.paths import repo_root


def scenarios_dir() -> Path:
    return repo_root() / "demo" / "scenarios"


def list_packs() -> list[dict[str, Any]]:
    root = scenarios_dir()
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        try:
            doc = load_pack(path.stem)
            out.append(
                {
                    "id": doc["id"],
                    "display_name": doc.get("display_name", doc["id"]),
                    "description": doc.get("description", ""),
                    "path": str(path),
                    "scenario_count": len(doc.get("scenarios") or []),
                    "coverage": doc.get("coverage") or {},
                }
            )
        except (ScenarioSchemaError, OSError, yaml.YAMLError) as exc:
            out.append(
                {
                    "id": path.stem,
                    "display_name": path.stem,
                    "description": f"INVALID: {exc}",
                    "path": str(path),
                    "scenario_count": 0,
                    "error": str(exc),
                }
            )
    return out


def load_pack(pack_id: str, *, path: Path | None = None) -> dict[str, Any]:
    """Load and validate a scenario pack by id (filename stem) or explicit path."""
    pack_path = path or (scenarios_dir() / f"{pack_id}.yaml")
    if not pack_path.is_file():
        raise FileNotFoundError(f"Scenario pack not found: {pack_path}")
    raw = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ScenarioSchemaError("pack root must be a mapping")
    raw.setdefault("id", pack_path.stem)
    return assert_valid_pack(raw, pack_id=pack_path.stem)


def expand_requests(
    pack: dict[str, Any],
    *,
    max_requests: int = 8000,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Expand pack scenarios into concrete request specs (deterministic).

    - Fixed scenarios with ``prompt`` emit one request each.
    - Scenarios with ``prompts`` pick the first (or seeded) variant.
    - Packs with ``mix`` + ``generate_count`` synthesize additional requests
      from scenario templates matching mix weights (enterprise-mixed).
    """
    import random

    rng = random.Random(seed)
    scenarios = list(pack.get("scenarios") or [])
    generate_count = pack.get("generate_count")
    mix = pack.get("mix")

    concrete: list[dict[str, Any]] = []

    if mix and generate_count:
        # Weighted sampling from scenarios that declare use_case_hint / mix_key
        by_key: dict[str, list[dict[str, Any]]] = {}
        for sc in scenarios:
            key = (
                (sc.get("request") or {}).get("use_case_hint")
                or (sc.get("expected") or {}).get("classification", {}).get("use_case")
                or sc.get("mix_key")
                or sc.get("id")
            )
            by_key.setdefault(str(key), []).append(sc)
        keys = list(mix.keys())
        weights = [float(mix[k]) for k in keys]
        n = min(int(generate_count), max_requests)
        for i in range(n):
            pick = rng.choices(keys, weights=weights, k=1)[0]
            pool = by_key.get(pick) or scenarios
            sc = rng.choice(pool)
            concrete.append(_materialize(sc, rng=rng, index=i))
        return concrete[:max_requests]

    for i, sc in enumerate(scenarios):
        if len(concrete) >= max_requests:
            break
        concrete.append(_materialize(sc, rng=rng, index=i))
    return concrete


def _materialize(
    sc: dict[str, Any],
    *,
    rng: Any,
    index: int,
) -> dict[str, Any]:
    req = dict(sc.get("request") or {})
    prompts = req.get("prompts")
    if prompts and isinstance(prompts, list) and prompts:
        prompt = prompts[rng.randrange(len(prompts))] if len(prompts) > 1 else prompts[0]
    else:
        prompt = req.get("prompt") or ""
    return {
        "scenario_id": sc["id"],
        "display_name": sc.get("display_name") or sc["id"],
        "prompt": prompt,
        "use_case_hint": req.get("use_case_hint"),
        "serving_pattern": req.get("serving_pattern"),
        "objective": req.get("objective"),
        "policy_context": dict(sc.get("policy_context") or {}),
        "expected": dict(sc.get("expected") or {}),
        "validation": dict(sc.get("validation") or {}),
        "inject": list(sc.get("inject") or []),
        "index": index,
        "story": sc.get("story"),
        "notes": sc.get("notes"),
    }
