#!/usr/bin/env python3
"""Generate catalog/aims.yaml from AMD accelerator support matrix."""

from __future__ import annotations

from pathlib import Path

import yaml

INSTINCT_ROWS = [
    ("CohereLabs/command-a-reasoning-08-2025", {"MI250X": "unoptimized", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("deepseek-ai/DeepSeek-R1", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("deepseek-ai/DeepSeek-R1-0528", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("deepseek-ai/DeepSeek-V3.1", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("deepseek-ai/DeepSeek-V3.1-Terminus", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("google/gemma-3-1b-it", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("google/gemma-3-27b-it", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("google/gemma-4-31B-it", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("google/medgemma-27b-it", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("meta-llama/Llama-3.1-405B-Instruct", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("meta-llama/Llama-3.1-8B-Instruct", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("meta-llama/Llama-3.2-1B-Instruct", {"MI250X": "general", "MI300X": "preview", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("meta-llama/Llama-3.2-3B-Instruct", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("meta-llama/Llama-3.3-70B-Instruct", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("MiniMaxAI/MiniMax-M2.5", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Ministral-3-14B-Instruct-2512", {"MI250X": "general", "MI300X": "unoptimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Ministral-3-14B-Reasoning-2512", {"MI250X": "general", "MI300X": "unoptimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Mistral-Large-3-675B-Instruct-2512", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Mistral-Small-24B-Instruct-2501", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Mistral-Small-3.2-24B-Instruct-2506", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Mixtral-8x22B-Instruct-v0.1", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("mistralai/Mixtral-8x7B-Instruct-v0.1", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("openai/gpt-oss-120b", {"MI250X": "unoptimized", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("openai/gpt-oss-20b", {"MI250X": "unoptimized", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("Qwen/Qwen3-235B-A22B", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("Qwen/Qwen3-32B", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "preview", "MI355X": "preview"}),
    ("Qwen/Qwen3-Coder-Next", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("Qwen/Qwen3-VL-235B-A22B-Instruct", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("Qwen/Qwen3-VL-235B-A22B-Thinking", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
    ("zai-org/GLM-4.7", {"MI250X": "general", "MI300X": "optimized", "MI325X": "unoptimized", "MI350X": "optimized", "MI355X": "optimized"}),
]

EPYC_ROWS = [
    ("google/gemma-4-E4B-it", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("meta-llama/Llama-3.1-8B-Instruct", {"EPYC_9965": "preview", "EPYC_ZEN4": "unoptimized", "EPYC_ZEN5": "unoptimized"}),
    ("meta-llama/Llama-3.2-1B-Instruct", {"EPYC_9965": "preview", "EPYC_ZEN4": "unoptimized", "EPYC_ZEN5": "unoptimized"}),
    ("meta-llama/Llama-3.2-3B-Instruct", {"EPYC_9965": "preview", "EPYC_ZEN4": "unoptimized", "EPYC_ZEN5": "unoptimized"}),
    ("Qwen/Qwen3-30B-A3B", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("Qwen/Qwen3-8B", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("Qwen/Qwen3.5-4B", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("Qwen/Qwen3.5-9B", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("Qwen/Qwen3.6-35B-A3B", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
    ("unsloth/gpt-oss-20b-BF16", {"EPYC_9965": "preview", "EPYC_ZEN4": "general", "EPYC_ZEN5": "unoptimized"}),
]

RADEON_ROWS = [
    ("google/gemma-3n-E4B-it", {"R9700": "preview", "W7900": "preview"}),
    ("meta-llama/Llama-3.1-8B-Instruct", {"R9700": "preview", "W7900": "preview"}),
    ("Qwen/Qwen3-VL-8B-Instruct", {"R9700": "preview", "W7900": "preview"}),
    ("Qwen/Qwen3.5-9B", {"R9700": "preview", "W7900": "preview"}),
    ("zai-org/GLM-4.7-Flash", {"R9700": "preview", "W7900": "preview"}),
]


def main() -> None:
    aims: dict[str, dict] = {}
    for model, support in INSTINCT_ROWS:
        aims.setdefault(model, {"model": model, "support": {}})["support"]["instinct"] = support
    for model, support in EPYC_ROWS:
        aims.setdefault(model, {"model": model, "support": {}})["support"]["epyc"] = support
    for model, support in RADEON_ROWS:
        aims.setdefault(model, {"model": model, "support": {}})["support"]["radeon"] = support

    catalog = {
        "version": "1",
        "metadata": {
            "source": "https://enterprise-ai.docs.amd.com/en/latest/aims/accelerator_support.html",
            "rocm_recommended": "7.2.3",
            "rocm_radeon_required": "7.13",
            "support_levels": ["optimized", "preview", "unoptimized", "general"],
            "last_refreshed": "2026-09-13",
        },
        "accelerators": {
            "instinct": ["MI250X", "MI300X", "MI325X", "MI350X", "MI355X"],
            "epyc": ["EPYC_9965", "EPYC_ZEN4", "EPYC_ZEN5"],
            "radeon": ["R9700", "W7900"],
        },
        "aims": sorted(aims.values(), key=lambda x: x["model"]),
    }
    out = Path(__file__).resolve().parents[1] / "catalog" / "aims.yaml"
    out.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out} ({len(catalog['aims'])} aims)")


if __name__ == "__main__":
    main()
