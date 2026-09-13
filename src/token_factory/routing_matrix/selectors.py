"""Distinct summary-card selection algorithms (not relabeled global ranks).

BEST PERFORMANCE  — maximize capability/performance; economics only tie-break
BEST BALANCE      — multi-fit trade-off; may diverge when economics are materially better
LOWEST-COST SUFFICIENT — constrained optimization: floor → filters → cheapest sufficient
BEST BATCH / BEST LOCAL — optional context cards
"""

from __future__ import annotations

from typing import Any, Callable

from token_factory.catalog.eligibility import SUPPORT_RANK

LEVEL_ORDER = {
    "PREFERRED": 5,
    "RECOMMENDED": 4,
    "ACCEPTABLE": 3,
    "SUPPORTED": 2,
    "NOT_SUPPORTED": 1,
}


def _spec_match(engine: Any, model: str, use_case: dict[str, Any]) -> bool:
    meta = engine.models.get(model, {})
    return bool(meta.get("specialization") and meta.get("specialization") == use_case.get("category"))


def _chars(engine: Any, compute_id: str) -> dict[str, Any]:
    return (engine.compute.get(compute_id, {}).get("characteristics") or {})


def select_best_performance(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
) -> Any | None:
    """Maximize capability/performance; economics only as tie-break."""
    eligible = [c for c in pool if not getattr(c, "lifecycle_excluded", False)]
    if not eligible:
        return None

    def key(c: Any) -> tuple:
        return (
            c.performance_fit,
            c.capability_fit,
            SUPPORT_RANK.get(c.aim_support, 0),
            1 if _spec_match(engine, c.model, use_case) else 0,
            LEVEL_ORDER.get(c.recommendation, 0),
            # Economics ONLY as tie-break (higher economic_fit / lower HW cost wins ties)
            round(c.economic_fit, 3),
            -engine._hw_cost_rank(c.compute_id),
            c.model,
            c.compute_id,
        )

    best = max(eligible, key=key)
    best.preference_label = "PERFORMANCE_PREFERRED"
    return best


def select_best_balance(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
    use_case_id: str,
    perf_leader: Any | None,
    utilization: str,
    serving_pattern: str,
    data_locality: bool = False,
) -> tuple[Any | None, list[str]]:
    """Trade capability/quality/perf/AIM/econ/deployment/traffic/lifecycle/serving.

    Must be able to pick a different model and/or compute than Performance when a
    sufficient candidate has materially better economics.
    """
    floor = engine._floor_tier(use_case_id)
    eligible = [
        c
        for c in pool
        if not getattr(c, "lifecycle_excluded", False)
        and engine._model_tier(c.model) >= floor
        and c.capability_fit >= 0.55
    ]
    if not eligible:
        eligible = [c for c in pool if not getattr(c, "lifecycle_excluded", False)]
    if not eligible:
        return None, []

    # Soft threshold: avoid auto-picking very-high-cost weak economic_fit
    has_reasonable_econ = any(
        c.economic_fit >= 0.35 and c.hardware_cost_class not in ("very-high",)
        for c in eligible
    )

    def balance_score(c: Any) -> float:
        aim_n = SUPPORT_RANK.get(c.aim_support, 0) / 4.0
        score = (
            c.capability_fit * 0.20
            + c.performance_fit * 0.18
            + c.economic_fit * 0.20
            + getattr(c, "deployment_fit", 0.5) * 0.10
            + c.lifecycle_fit * 0.10
            + getattr(c, "serving_pattern_fit", 0.5) * 0.10
            + getattr(c, "locality_fit", 0.5) * 0.07
            + aim_n * 0.05
        )
        if _spec_match(engine, c.model, use_case):
            score += 0.08

        chars = _chars(engine, c.compute_id)
        if utilization == "high" and chars.get("high_throughput"):
            score += 0.06
        if utilization == "low" and (
            chars.get("cpu_inference")
            or chars.get("local_workstation")
            or chars.get("pcie_form_factor")
        ):
            score += 0.05
        if serving_pattern in ("batch", "offline-batch") and chars.get("cpu_inference"):
            score += 0.06
        if data_locality and chars.get("data_local"):
            score += 0.12

        if perf_leader is not None:
            same = c.model == perf_leader.model and c.compute_id == perf_leader.compute_id
            if not same:
                econ_delta = c.economic_fit - perf_leader.economic_fit
                perf_delta = c.performance_fit - perf_leader.performance_fit
                hw_delta = engine._hw_cost_rank(perf_leader.compute_id) - engine._hw_cost_rank(
                    c.compute_id
                )
                if econ_delta >= 0.15 and perf_delta >= -0.20 and c.capability_fit >= 0.85:
                    score += 0.14
                elif hw_delta >= 1 and econ_delta > 0 and perf_delta >= -0.15:
                    score += 0.12
                if (
                    c.model == perf_leader.model
                    and hw_delta >= 1
                    and _spec_match(engine, c.model, use_case)
                ):
                    score += 0.10

        if has_reasonable_econ and c.hardware_cost_class == "very-high" and c.economic_fit < 0.35:
            score -= 0.16
        return score

    best = max(eligible, key=lambda c: (balance_score(c), c.economic_fit, -engine._hw_cost_rank(c.compute_id)))
    best.preference_label = "BALANCED_PREFERRED"

    why: list[str] = []
    if perf_leader is not None:
        same = best.model == perf_leader.model and best.compute_id == perf_leader.compute_id
        if not same:
            why.append(
                f"Chose {best.model} × {best.compute_id} over performance leader "
                f"{perf_leader.model} × {perf_leader.compute_id}: materially better "
                f"economic_fit ({best.economic_fit:.2f} vs {perf_leader.economic_fit:.2f}) "
                f"while remaining capability/performance-sufficient "
                f"(cap {best.capability_fit:.2f}, perf {best.performance_fit:.2f})."
            )
            if best.model == perf_leader.model:
                why.append(
                    f"Same model on lower infrastructure cost class "
                    f"({best.hardware_cost_class} vs {perf_leader.hardware_cost_class})."
                )
            if _spec_match(engine, best.model, use_case):
                why.append(f"Specialization matches use-case category '{use_case.get('category')}'.")
        else:
            why.append(
                "Balance agrees with performance leader on this workload "
                "(no sufficient lower-cost alternative cleared the trade-off)."
            )
    return best, why


def select_lowest_cost_sufficient(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
    use_case_id: str,
) -> Any | None:
    """Constrained optimization: floor → filters → economically lowest among sufficient.

    Never: smallest model = sufficient, or cheapest HW = best economics without a floor.
    """
    floor = engine._floor_tier(use_case_id)
    sufficient = [
        c
        for c in pool
        if not getattr(c, "lifecycle_excluded", False)
        and engine._model_tier(c.model) >= floor
        and c.capability_fit >= 0.70
    ]
    if not sufficient:
        return None

    def key(c: Any) -> tuple:
        overshoot = engine._model_tier(c.model) - floor
        # Prefer meeting floor without huge overkill; specialization as soft preference
        return (
            engine._hw_cost_rank(c.compute_id),
            -round(c.economic_fit, 3),
            overshoot,
            0 if _spec_match(engine, c.model, use_case) else 1,
            -SUPPORT_RANK.get(c.aim_support, 0),
            c.model,
            c.compute_id,
        )

    best = min(sufficient, key=key)
    best.preference_label = "ECONOMIC_PREFERRED"
    return best


def select_best_batch(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
    use_case_id: str,
) -> Any | None:
    """Batch / offline: favor EPYC / relaxed-latency-friendly compute among sufficient."""
    floor = engine._floor_tier(use_case_id)
    eligible = [
        c
        for c in pool
        if not getattr(c, "lifecycle_excluded", False)
        and engine._model_tier(c.model) >= floor
        and c.capability_fit >= 0.70
    ]
    if not eligible:
        return None

    def key(c: Any) -> tuple:
        chars = _chars(engine, c.compute_id)
        batch_affinity = 0
        if chars.get("cpu_inference"):
            batch_affinity += 3
        if chars.get("pcie_form_factor"):
            batch_affinity += 1
        if chars.get("high_concurrency") and not chars.get("cpu_inference"):
            batch_affinity -= 1
        return (
            batch_affinity,
            round(c.economic_fit, 3),
            round(getattr(c, "serving_pattern_fit", 0.5), 3),
            -engine._hw_cost_rank(c.compute_id),
            round(c.capability_fit, 3),
            c.model,
        )

    best = max(eligible, key=key)
    best.preference_label = "BATCH_PREFERRED"
    return best


def select_best_local(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
    use_case_id: str,
) -> Any | None:
    """Locality / privacy: capable local (Radeon) wins; incapable never."""
    floor = engine._floor_tier(use_case_id)
    local = [
        c
        for c in pool
        if not getattr(c, "lifecycle_excluded", False)
        and engine._model_tier(c.model) >= floor
        and c.capability_fit >= 0.70
        and _chars(engine, c.compute_id).get("data_local")
    ]
    if not local:
        return None

    def key(c: Any) -> tuple:
        return (
            round(getattr(c, "locality_fit", 0.5), 3),
            round(c.capability_fit, 3),
            round(c.performance_fit, 3),
            1 if _spec_match(engine, c.model, use_case) else 0,
            SUPPORT_RANK.get(c.aim_support, 0),
            c.model,
        )

    best = max(local, key=key)
    best.preference_label = "LOCAL_PREFERRED"
    return best


def clone_candidate(c: Any) -> Any:
    """Shallow-copy a Candidate so card labels do not mutate the shared pool."""
    from copy import copy

    return copy(c)


def apply_card_selection(
    engine: Any,
    pool: list[Any],
    *,
    use_case: dict[str, Any],
    use_case_id: str,
    utilization: str,
    serving_pattern: str,
    data_locality: bool,
    locality_preferred: bool,
) -> dict[str, Any]:
    """Run distinct selectors; return card dicts."""
    from copy import copy

    working = [copy(c) for c in pool]

    perf = select_best_performance(engine, working, use_case=use_case)
    bal, bal_why = select_best_balance(
        engine,
        working,
        use_case=use_case,
        use_case_id=use_case_id,
        perf_leader=perf,
        utilization=utilization,
        serving_pattern=serving_pattern,
        data_locality=data_locality,
    )
    lcs = select_lowest_cost_sufficient(
        engine, working, use_case=use_case, use_case_id=use_case_id
    )

    def pack(label: str, obj: str, cand: Any | None, extra: dict | None = None) -> dict:
        tp = False
        out_label = label
        if cand and cand.lifecycle in ("tech-preview", "preview"):
            tp = True
            tag = "TECH PREVIEW" if cand.lifecycle == "tech-preview" else "PREVIEW"
            out_label = f"{label} · {tag}"
        d: dict[str, Any] = {
            "label": out_label,
            "objective": obj,
            "candidate": cand.to_dict() if cand else None,
            "tech_preview": tp,
            "selection": obj,
        }
        if extra:
            d.update(extra)
        return d

    cards = {
        "best_performance": pack("BEST PERFORMANCE", "performance", perf),
        "best_balance": pack(
            "BEST BALANCE",
            "balance",
            bal,
            {"why_not_performance": bal_why, "balance_rationale": bal_why},
        ),
        "lowest_cost_sufficient": pack(
            "LOWEST-COST SUFFICIENT", "lowest-cost-sufficient", lcs
        ),
    }

    if serving_pattern in ("batch", "offline-batch"):
        batch = select_best_batch(
            engine, working, use_case=use_case, use_case_id=use_case_id
        )
        cards["best_batch"] = pack("BEST BATCH", "batch", batch)

    if data_locality or locality_preferred:
        local = select_best_local(
            engine, working, use_case=use_case, use_case_id=use_case_id
        )
        cards["best_local"] = pack("BEST LOCAL", "local", local)

    return cards
