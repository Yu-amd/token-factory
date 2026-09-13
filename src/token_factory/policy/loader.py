"""Load canonical AMD policy + profile overlays (backward-compatible paths)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from token_factory.runtime.paths import repo_root

CANONICAL_REL = Path("policies/amd-policy.yaml")
LEGACY_CATALOG_REL = Path("catalog/amd-routing-policy.yaml")
PROFILES_DIR_REL = Path("policies/profiles")
LEGACY_PROFILES_DIR_REL = Path("policies")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a mapping")
    return data


def canonical_policy_path(root: Path | None = None) -> Path:
    root = root or repo_root()
    preferred = root / CANONICAL_REL
    if preferred.exists():
        return preferred
    legacy = root / LEGACY_CATALOG_REL
    if legacy.exists():
        return legacy
    return preferred


def load_canonical_policy(root: Path | None = None) -> dict[str, Any]:
    """Load the AMD canonical routing policy (engine-compatible flat + nested form)."""
    root = root or repo_root()
    path = canonical_policy_path(root)
    data = _load_yaml(path)

    # Follow redirect / compat shim from catalog/
    redirect = (data.get("metadata") or {}).get("redirect") or data.get("_redirect")
    if redirect and not data.get("overrides") and not (data.get("policy") or {}).get("overrides"):
        redirected = root / redirect
        if redirected.exists() and redirected.resolve() != path.resolve():
            data = _load_yaml(redirected)
            path = redirected

    # Normalize: ensure flat keys RecommendationEngine expects
    nested = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    out = deepcopy(data)
    meta = dict(out.get("metadata") or {})
    amd_meta = dict(meta.get("amd_routing_policy") or {})
    if nested.get("policy_version"):
        amd_meta.setdefault("version", nested["policy_version"])
    if nested.get("published"):
        amd_meta.setdefault("published", nested["published"])
    amd_meta.setdefault("canonical_path", str(CANONICAL_REL))
    meta["amd_routing_policy"] = amd_meta
    out["metadata"] = meta

    for key in (
        "recommendation_levels",
        "aim_support_rank",
        "unoptimized_max_level",
        "lifecycle",
        "objective_compute_bias",
        "objective_size_bias",
        "escalation",
        "overrides",
    ):
        if key not in out or out[key] is None:
            if nested.get(key) is not None:
                out[key] = nested[key]

    if "version" not in out:
        out["version"] = nested.get("policy_version") or amd_meta.get("version") or "2.4"

    out["_source_path"] = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
    out["_canonical"] = nested or None
    return out


def resolve_profile_path(name: str, root: Path | None = None) -> Path:
    """Resolve profile by name — profiles/ first, then legacy policies/{name}.yaml."""
    root = root or repo_root()
    name = name.removesuffix(".yaml")
    candidates = [
        root / PROFILES_DIR_REL / f"{name}.yaml",
        root / LEGACY_PROFILES_DIR_REL / f"{name}.yaml",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Policy profile not found: {name} (searched {[str(c) for c in candidates]})"
    )


def load_profile(name: str, root: Path | None = None) -> dict[str, Any]:
    path = resolve_profile_path(name, root)
    data = _load_yaml(path)
    data["_source_path"] = str(path)
    return data


def list_profiles(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or repo_root()
    known: dict[str, Path] = {}
    for base in (root / PROFILES_DIR_REL, root / LEGACY_PROFILES_DIR_REL):
        if not base.exists():
            continue
        for path in sorted(base.glob("amd-*.yaml")):
            # Prefer profiles/ over legacy duplicate
            if path.name not in known or PROFILES_DIR_REL.as_posix() in str(path):
                if path.name == "amd-policy.yaml":
                    continue
                # Skip if already taken from profiles/
                if path.parent.name == "profiles" or path.name not in known:
                    known[path.name] = path
    # Rebuild preferring profiles
    preferred: dict[str, Path] = {}
    for path in sorted((root / PROFILES_DIR_REL).glob("amd-*.yaml")) if (root / PROFILES_DIR_REL).exists() else []:
        preferred[path.stem] = path
    for path in sorted((root / LEGACY_PROFILES_DIR_REL).glob("amd-*.yaml")):
        if path.stem == "amd-policy":
            continue
        preferred.setdefault(path.stem, path)

    out = []
    for stem, path in sorted(preferred.items()):
        doc = _load_yaml(path)
        policy = doc.get("policy") or {}
        overlay = doc.get("overlay") or policy.get("overlay") or {}
        out.append(
            {
                "id": stem,
                "name": policy.get("name", stem),
                "description": policy.get("description"),
                "priority_mode": policy.get("priority_mode") or overlay.get("priority_mode"),
                "objective": overlay.get("objective") or policy.get("priority_mode"),
                "overlay": overlay,
                "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                "route_count": len(policy.get("routes") or []),
            }
        )
    return out


def apply_profile_overlay(
    canonical: dict[str, Any],
    profile: dict[str, Any] | str | None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Merge profile overlay onto canonical policy without duplicating use-case matrices.

    Profiles alter objective preference, lifecycle strictness, economics/locality bias,
    and V1 SR routes/fallback — they do not redefine compute positioning or eligibility.
    """
    effective = deepcopy(canonical)
    if profile is None:
        effective["_profile"] = None
        return effective
    if isinstance(profile, str):
        profile = load_profile(profile, root)
    overlay = profile.get("overlay") or (profile.get("policy") or {}).get("overlay") or {}
    policy_block = profile.get("policy") or {}

    nested = dict(effective.get("_canonical") or effective.get("policy") or {})
    # Overlay objective → alias into recommendation defaults
    if overlay.get("objective"):
        nested["active_objective"] = overlay["objective"]
        effective["active_objective"] = overlay["objective"]
    if overlay.get("lifecycle_strictness"):
        nested["active_lifecycle_mode"] = overlay["lifecycle_strictness"]
        effective["active_lifecycle_mode"] = overlay["lifecycle_strictness"]
    for key in (
        "economic_preference",
        "performance_preference",
        "locality_preference",
        "priority_mode",
    ):
        if overlay.get(key) is not None:
            nested[key] = overlay[key]
            effective[key] = overlay[key]

    # Soft bias nudges from locality preference (engine may read these)
    if overlay.get("locality_preference") == "prefer-local":
        biases = dict(effective.get("objective_compute_bias") or {})
        for obj in ("balanced", "edge-local", "latency"):
            biases[obj] = ["radeon", "epyc", "instinct"]
        effective["objective_compute_bias"] = biases
        nested["objective_compute_bias"] = biases

    effective["_canonical"] = nested
    effective["_profile"] = {
        "name": policy_block.get("name"),
        "priority_mode": policy_block.get("priority_mode"),
        "overlay": overlay,
        "virtual_model": policy_block.get("virtual_model"),
        "fallback": policy_block.get("fallback"),
        "routes": policy_block.get("routes"),
        "source_path": profile.get("_source_path"),
    }
    effective["policy_pack"] = policy_block
    return effective
