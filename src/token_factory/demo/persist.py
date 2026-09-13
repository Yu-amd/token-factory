"""Persist demo run artifacts under generated/demo-runs/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from token_factory.demo.models import DemoRun
from token_factory.runtime.paths import generated_dir, repo_root


def demo_runs_dir() -> Path:
    # Prefer repo generated/ so artifacts stay with the project; fall back if unwritable
    primary = repo_root() / "generated" / "demo-runs"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        alt = generated_dir() / "demo-runs"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def persist_run(run: DemoRun) -> Path:
    path = demo_runs_dir() / f"{run.id}.json"
    path.write_text(json.dumps(run.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def load_run(run_id: str) -> dict[str, Any]:
    path = demo_runs_dir() / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Demo run not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    root = demo_runs_dir()
    files = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in files[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.append(
                {
                    "run_id": data.get("run_id") or path.stem,
                    "scenario_pack": data.get("scenario_pack"),
                    "started_at": data.get("started_at"),
                    "completed_at": data.get("completed_at"),
                    "validation_summary": data.get("validation_summary") or {},
                    "path": str(path),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    return out
