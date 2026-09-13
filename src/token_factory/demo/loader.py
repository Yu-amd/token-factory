"""Load declarative Automated Demo scenario packs from demo/scenarios/."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from token_factory.demo.schema import ScenarioSchemaError, assert_valid_pack
from token_factory.runtime.paths import repo_root

# Keep in sync with runner.MAX_REQUESTS (avoid circular import).
_MAX_REQUESTS = 8000


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
    requests: int | None = None,
    seed: int | None = None,
    max_requests: int | None = None,
) -> list[dict[str, Any]]:
    """Expand pack scenarios into concrete request specs (deterministic).

    ``requests`` is the **target** workload size (clamped to ``_MAX_REQUESTS``).

    - **Mixed** packs (``mix`` present): generate ``n`` weighted samples.
      Pack YAML ``generate_count`` is the default when ``requests`` is omitted —
      not a hard cap when UI/CLI passes ``N``.
    - **Fixed** packs: emit each scenario once when ``requests`` is omitted;
      when ``requests=N``, cycle the scenario list (varying prompt index when
      multiple prompts exist) until ``N`` requests.

    ``max_requests`` is accepted as a deprecated alias for ``requests``.
    """
    if requests is None and max_requests is not None:
        requests = max_requests

    scenarios = list(pack.get("scenarios") or [])
    if not scenarios:
        return []

    mix = pack.get("mix")
    generate_count = pack.get("generate_count")

    if mix:
        import random

        rng = random.Random(seed)
        if requests is not None:
            n = min(int(requests), _MAX_REQUESTS)
        else:
            default_n = int(generate_count) if generate_count else len(scenarios)
            n = min(default_n, _MAX_REQUESTS)
        return _expand_mixed(scenarios, mix=mix, n=n, rng=rng)

    if requests is not None:
        n = min(int(requests), _MAX_REQUESTS)
        return _expand_fixed_cycled(scenarios, n=n)

    return [_materialize(sc, index=i) for i, sc in enumerate(scenarios)]


def _expand_mixed(
    scenarios: list[dict[str, Any]],
    *,
    mix: dict[str, Any],
    n: int,
    rng: Any,
) -> list[dict[str, Any]]:
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
    concrete: list[dict[str, Any]] = []
    for i in range(n):
        pick = rng.choices(keys, weights=weights, k=1)[0]
        pool = by_key.get(pick) or scenarios
        sc = rng.choice(pool)
        concrete.append(_materialize(sc, index=i))
    return concrete


def _expand_fixed_cycled(
    scenarios: list[dict[str, Any]],
    *,
    n: int,
) -> list[dict[str, Any]]:
    concrete: list[dict[str, Any]] = []
    for i in range(n):
        sc = scenarios[i % len(scenarios)]
        concrete.append(_materialize(sc, index=i))
    return concrete


def _materialize(
    sc: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    req = dict(sc.get("request") or {})
    prompts = req.get("prompts")
    if prompts and isinstance(prompts, list) and prompts:
        # Stable cycling across repeats (index % len); mixed scenario picks use seed.
        prompt = prompts[index % len(prompts)]
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
