"""Policies tab — AMD Opinionated Routing Policy (human-readable canonical policy)."""

from __future__ import annotations

import html as html_lib
import sys
from pathlib import Path
from typing import Any, Callable

import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value))


def render_policies_tab(
    meta: dict[str, Any],
    *,
    section: Callable[..., None],
    html: Callable[[str], None],
) -> None:
    """Render the redesigned Policies tab from compiled amd_policy metadata + live engine."""
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))

    from token_factory.policy import explain_policy, load_canonical_policy, policy_ui_metadata
    from token_factory.routing_matrix import RecommendationEngine

    # Prefer compiled metadata; refresh live if missing/partial
    pol = meta.get("amd_policy") if isinstance(meta.get("amd_policy"), dict) else {}
    if not pol or pol.get("available") is False or not pol.get("compute_positioning"):
        try:
            pol = policy_ui_metadata(profile_name=meta.get("policy_name"))
        except Exception as exc:
            section(
                "Policies",
                "AMD Opinionated Routing Policy",
                f"Unable to load canonical policy: {exc}",
            )
            return

    version = pol.get("version") or "2.3"
    counts = pol.get("counts") or {}
    positioning = pol.get("compute_positioning") or {}
    eligibility = pol.get("eligibility") or {}
    hard_gates = pol.get("eligibility_rules") or eligibility.get("hard_gates") or []
    objectives = pol.get("objectives") or {}
    serving = pol.get("serving_patterns") or {}
    coverage = pol.get("coverage") or {}
    fallback = pol.get("fallback_policy") or {}
    canon_vs = pol.get("canonical_vs_runtime") or {}
    pipeline = pol.get("decision_pipeline") or []
    scenarios = pol.get("scenarios") or []
    profiles = pol.get("profile_comparison") or pol.get("profiles") or []

    section(
        "Policies",
        "AMD Opinionated Routing Policy",
        "The rules behind the Routing Matrix — one canonical SHOULD RUN source shared by "
        "Matrix, Explain Policy, simulation, fallback, and compiled routes. "
        "AIM catalog remains CAN RUN authority. Private-eval ≠ production-eligible.",
        hero=True,
        meta=[
            ("Policy", f"amd-routing-policy v{version}"),
            ("Profile", pol.get("active_profile") or meta.get("policy_name") or "amd-balanced"),
            ("Source", pol.get("source_path") or "policies/amd-policy.yaml"),
        ],
    )

    # --- 1. Policy Overview ---
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">1 · Policy Overview</p>
          <h2 class="tf-h2">Canonical policy metadata</h2>
          <p class="tf-sub">{_esc(pol.get("description") or "")}</p>
          <dl class="tf-kv">
            <dt>Policy</dt><dd>{_esc(pol.get("id"))}</dd>
            <dt>Version</dt><dd>{_esc(version)}</dd>
            <dt>Active profile</dt><dd>{_esc(pol.get("active_profile"))}</dd>
            <dt>Virtual model</dt><dd>{_esc(pol.get("virtual_model"))}</dd>
            <dt>Published</dt><dd>{_esc(pol.get("published"))}</dd>
            <dt>Source</dt><dd>{_esc(pol.get("source_path"))}</dd>
          </dl>
          <div class="tf-chips" style="margin-top:0.85rem">
            <span class="tf-chip">Use cases {_esc(counts.get("use_cases"))}</span>
            <span class="tf-chip">Compute {_esc(counts.get("compute_targets"))}</span>
            <span class="tf-chip">Models {_esc(counts.get("models"))}</span>
            <span class="tf-chip">Objectives {_esc(counts.get("objectives"))}</span>
            <span class="tf-chip">Lifecycle modes {_esc(counts.get("lifecycle_modes"))}</span>
            <span class="tf-chip">Hard gates {_esc(counts.get("hard_gates"))}</span>
            <span class="tf-chip">Capability gates {_esc(counts.get("capability_gates"))}</span>
          </div>
        </div>
        """
    )

    # --- 2. Decision Pipeline ---
    pipe_html = " → ".join(f"<span class='tf-chip'>{_esc(s)}</span>" for s in pipeline)
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">2 · Decision Pipeline</p>
          <h2 class="tf-h2">Policy vs catalog vs runtime</h2>
          <p class="tf-sub">
            <span class="tf-mono">AIM = CAN RUN</span> ·
            <span class="tf-mono">Policy = SHOULD RUN</span> ·
            <span class="tf-mono">Inventory = AVAILABLE NOW</span> ·
            <span class="tf-mono">Compiled = ACTIVE EXECUTION</span>
          </p>
          <div style="margin-top:0.75rem;line-height:2.1">{pipe_html}</div>
        </div>
        """
    )

    # --- 3. Eligibility / Guardrails ---
    gates_html = "".join(
        f"<li><strong>{_esc(g.get('id'))}</strong> — {_esc(g.get('rule'))}</li>"
        for g in hard_gates
        if isinstance(g, dict)
    )
    cap_gates = eligibility.get("capability_gates") or {}
    cap_html = "".join(
        f"<li><span class='tf-mono'>{_esc(k)}</span> — {_esc(v)}</li>"
        for k, v in cap_gates.items()
    )
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">3 · Eligibility / Guardrails</p>
          <h2 class="tf-h2">Hard gates (not preference scores)</h2>
          <ul class="tf-sub" style="margin:0.5rem 0 0;padding-left:1.2rem">{gates_html or "<li>None declared</li>"}</ul>
          <p class="tf-sub" style="margin-top:0.85rem"><strong>Capability gates</strong></p>
          <ul class="tf-sub" style="margin:0.35rem 0 0;padding-left:1.2rem">{cap_html or "<li>—</li>"}</ul>
        </div>
        """
    )

    # --- 4. AMD Compute Positioning ---
    continuum = positioning.get("continuum") or []
    cont_cells = "".join(
        f"""<div style="flex:1;min-width:140px;padding:0.75rem;border:1px solid var(--tf-border);
            border-radius:0.5rem;background:var(--tf-elevated)">
            <div style="font-weight:600;color:var(--tf-green-hi)">{_esc(c.get('label'))}</div>
            <div class="tf-sub">{_esc(c.get('role'))}</div>
          </div>"""
        for c in continuum
    )
    cards = []
    for key, title in (
        ("instinct", "Instinct"),
        ("mi350p", "MI350P"),
        ("radeon", "Radeon"),
        ("epyc", "EPYC"),
    ):
        block = positioning.get(key) or {}
        cards.append(
            f"""<div class="tf-card" style="margin-bottom:0.65rem">
              <p class="tf-eyebrow">{_esc(title)}</p>
              <p class="tf-sub">{_esc(block.get("statement"))}</p>
              <div class="tf-chips" style="margin-top:0.5rem">
                <span class="tf-chip">{_esc(block.get("role"))}</span>
              </div>
            </div>"""
        )
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">4 · AMD Compute Positioning</p>
          <h2 class="tf-h2">Deployment continuum</h2>
          <p class="tf-sub">{_esc(positioning.get("continuum_label") or "Deployment positioning — not a benchmark ranking")}</p>
          <div style="display:flex;gap:0.65rem;flex-wrap:wrap;margin:0.85rem 0">{cont_cells}</div>
          <p class="tf-sub">{_esc(positioning.get("epyc_note"))}</p>
        </div>
        {"".join(cards)}
        """
    )

    # --- 5. Objective Profiles ---
    obj_rows = []
    for oid, ob in objectives.items():
        if not isinstance(ob, dict):
            continue
        obj_rows.append(
            {
                "Objective": ob.get("display_name") or oid,
                "Id": ob.get("id") or oid,
                "Summary": ob.get("summary") or "",
            }
        )
    html(
        """
        <div class="tf-card">
          <p class="tf-eyebrow">5 · Objective Profiles</p>
          <h2 class="tf-h2">What we optimize</h2>
          <p class="tf-sub">Profiles are overlays on the canonical policy — they do not duplicate use-case matrices.</p>
        </div>
        """
    )
    if obj_rows:
        st.dataframe(obj_rows, width="stretch", hide_index=True)

    # Profile comparison
    cmp_rows = []
    for p in profiles:
        if not isinstance(p, dict):
            continue
        cmp_rows.append(
            {
                "Profile": p.get("profile") or p.get("id") or p.get("name"),
                "Primary objective": p.get("primary_objective") or p.get("objective"),
                "Lifecycle bias": p.get("lifecycle_bias"),
                "Economics": p.get("economics"),
                "Locality": p.get("locality"),
                "Typical use": p.get("typical_use") or "",
            }
        )
    if cmp_rows:
        st.caption("Profile comparison (overlay metadata)")
        st.dataframe(cmp_rows, width="stretch", hide_index=True)

    # --- 6. Serving Patterns ---
    serve_rows = []
    for sp_id, sp in serving.items():
        if not isinstance(sp, dict):
            continue
        serve_rows.append(
            {
                "Pattern": sp.get("display_name") or sp_id,
                "Optimizes for": sp.get("optimizes_for"),
                "Compute tendency": sp.get("compute_tendency"),
                "Default latency": sp.get("default_latency"),
            }
        )
    html(
        """
        <div class="tf-card">
          <p class="tf-eyebrow">6 · Serving Patterns</p>
          <h2 class="tf-h2">Interactive ≠ high traffic · Batch ≠ high-concurrency interactive</h2>
        </div>
        """
    )
    if serve_rows:
        st.dataframe(serve_rows, width="stretch", hide_index=True)

    # --- 7. Use-Case Policy Coverage ---
    html(
        """
        <div class="tf-card">
          <p class="tf-eyebrow">7 · Use-Case Policy Coverage</p>
          <h2 class="tf-h2">Generated from the use-case catalog</h2>
          <p class="tf-sub">Every use case has a GA path, an explicit preview/TP-only path, or a declared gap.
          Full cell detail lives in the Routing Matrix — not duplicated here.</p>
        </div>
        """
    )
    cov_counts = coverage.get("counts") or counts
    st.caption(
        f"GA-capable {cov_counts.get('ga_capable', '—')} · "
        f"Preview-only {cov_counts.get('preview_only', '—')} · "
        f"Tech-preview-only {cov_counts.get('tech_preview_only', '—')} · "
        f"Gaps {cov_counts.get('no_eligible_candidate', '—')}"
    )
    uc_rows = coverage.get("use_cases") or []
    cat_opts = sorted({r.get("category") or "—" for r in uc_rows}) if uc_rows else []
    status_opts = ["all", "ga-capable", "preview-only", "tech-preview-only", "no-eligible-candidate"]
    f1, f2, f3 = st.columns(3)
    with f1:
        filt_cat = st.selectbox("Filter category", ["all", *cat_opts], key="pol_cov_cat")
    with f2:
        filt_status = st.selectbox("Filter status", status_opts, key="pol_cov_status")
    with f3:
        filt_q = st.text_input("Search use case", "", key="pol_cov_q")

    table_rows = []
    for r in uc_rows:
        if filt_cat != "all" and (r.get("category") or "—") != filt_cat:
            continue
        if filt_status != "all" and r.get("status") != filt_status:
            continue
        if filt_q and filt_q.lower() not in (r.get("display_name") or "").lower() and filt_q.lower() not in (
            r.get("use_case") or ""
        ).lower():
            continue
        prod = r.get("paths", {}).get("production") or []
        top = prod[0] if prod else (r.get("paths", {}).get("evaluation") or [None])[0]
        table_rows.append(
            {
                "Use case": r.get("display_name"),
                "Id": r.get("use_case"),
                "Category": r.get("category"),
                "Status": r.get("status"),
                "Default objective": r.get("objective_default"),
                "Serving": r.get("serving_pattern_default"),
                "Top path": (
                    f"{top.get('model')} × {top.get('compute')}" if isinstance(top, dict) else "—"
                ),
                "Gap": r.get("gap") or "",
            }
        )
    if table_rows:
        st.dataframe(table_rows, width="stretch", hide_index=True)
    st.caption("View full projection in the AMD Routing Matrix tab.")

    # --- 8. Explain Policy explorer ---
    html(
        """
        <div class="tf-card">
          <p class="tf-eyebrow">8 · Explain Policy</p>
          <h2 class="tf-h2">Interactive policy explorer</h2>
          <p class="tf-sub">Same RecommendationEngine as the Routing Matrix — steps 1–7, no hard-coded winners.</p>
        </div>
        """
    )
    try:
        engine = RecommendationEngine()
        uc_opts = {u["display_name"]: u["id"] for u in engine.list_use_cases()}
        obj_opts = {o["display_name"]: o["id"] for o in engine.list_objectives()}
        life_opts = {m["display_name"]: m["id"] for m in engine.list_lifecycle_modes()}
        serve_opts = {s["display_name"]: s["id"] for s in engine.list_serving_patterns()}
    except Exception as exc:
        st.error(f"Engine unavailable: {exc}")
        return

    # Scenario buttons
    scenario_cols = st.columns(min(5, max(1, len(scenarios))))
    for i, sc in enumerate(scenarios[:5]):
        with scenario_cols[i]:
            if st.button(sc.get("label", sc.get("id")), key=f"pol_sc_{sc.get('id')}"):
                st.session_state["pol_scenario"] = sc

    sc = st.session_state.get("pol_scenario") or (scenarios[0] if scenarios else {})
    default_uc = sc.get("use_case") or "coding-assistant"
    default_obj = sc.get("objective") or "balanced"
    default_serve = sc.get("serving_pattern") or "interactive"
    default_life = sc.get("lifecycle") or "production"
    default_traffic = sc.get("traffic") or "medium"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        uc_names = list(uc_opts.keys())
        uc_ids = list(uc_opts.values())
        uc_idx = uc_ids.index(default_uc) if default_uc in uc_ids else 0
        uc_label = st.selectbox("Use Case", uc_names, index=uc_idx, key="pol_uc")
    with c2:
        obj_ids = list(obj_opts.values())
        obj_idx = obj_ids.index(default_obj) if default_obj in obj_ids else 0
        obj_label = st.selectbox("Objective", list(obj_opts.keys()), index=obj_idx, key="pol_obj")
    with c3:
        serve_ids = list(serve_opts.values())
        serve_idx = serve_ids.index(default_serve) if default_serve in serve_ids else 0
        serve_label = st.selectbox(
            "Serving", list(serve_opts.keys()), index=serve_idx, key="pol_serve"
        )
    with c4:
        traffic = st.selectbox(
            "Traffic",
            ["low", "medium", "high"],
            index=["low", "medium", "high"].index(default_traffic)
            if default_traffic in ("low", "medium", "high")
            else 1,
            key="pol_traffic",
        )
    with c5:
        life_ids = list(life_opts.values())
        life_idx = life_ids.index(default_life) if default_life in life_ids else 0
        life_label = st.selectbox(
            "Lifecycle", list(life_opts.keys()), index=life_idx, key="pol_life"
        )

    data_locality = st.checkbox(
        "Data locality / local-first",
        value=bool(sc.get("data_locality")),
        key="pol_locality",
    )

    explained = explain_policy(
        uc_opts[uc_label],
        objective=obj_opts[obj_label],
        serving_pattern=serve_opts[serve_label],
        traffic=traffic,
        lifecycle=life_opts[life_label],
        data_locality=data_locality,
    )
    for step in explained.get("steps") or []:
        with st.expander(f"Step {step['step']} — {step['title']}", expanded=step["step"] <= 2):
            if step["step"] == 1:
                st.write(
                    {
                        "required": step.get("required"),
                        "preferred": step.get("preferred"),
                        "capability_floor": step.get("capability_floor"),
                    }
                )
            elif step["step"] == 2:
                st.write(
                    {
                        "lifecycle_mode": step.get("lifecycle_mode"),
                        "allowed": step.get("allowed_lifecycles"),
                        "exclusions": step.get("lifecycle_exclusions"),
                    }
                )
                for note in (step.get("notes") or [])[:6]:
                    st.caption(note)
            elif step["step"] == 3:
                for note in step.get("notes") or []:
                    st.write(note)
                st.caption(
                    f"serving={step.get('serving_pattern')} · latency={step.get('latency_requirement')} · "
                    f"traffic={step.get('traffic')}"
                )
            elif step["step"] == 4:
                st.write(
                    {
                        "objective": step.get("objective"),
                        "preference_label": step.get("preference_label"),
                        "meta": step.get("objective_meta"),
                    }
                )
            elif step["step"] == 5:
                st.dataframe(step.get("candidates") or [], width="stretch", hide_index=True)
            elif step["step"] == 6:
                st.write(step.get("selected_runtime_route") or "No deployed eligible endpoint")
                st.caption(step.get("explanation") or "")
            elif step["step"] == 7:
                for rule in step.get("canonical_rules") or []:
                    st.markdown(f"- {rule}")
                chain = step.get("profile_fallback_chain") or []
                if chain:
                    st.caption("V1 profile fallback: " + " → ".join(chain))

    # --- 9. Fallback Policy ---
    rules_html = "".join(f"<li>{_esc(r)}</li>" for r in (fallback.get("rules") or []))
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">9 · Fallback Policy</p>
          <h2 class="tf-h2">When the primary path is unavailable</h2>
          <ul class="tf-sub" style="margin:0.5rem 0 0;padding-left:1.2rem">{rules_html}</ul>
          <p class="tf-sub" style="margin-top:0.65rem">V1 chain source: <span class="tf-mono">{_esc(fallback.get("v1_chain_source"))}</span></p>
        </div>
        """
    )

    # --- 10. Canonical vs Effective Runtime ---
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">10 · Canonical vs Effective Runtime Policy</p>
          <h2 class="tf-h2">Same source — different projections</h2>
          <dl class="tf-kv">
            <dt>AIM catalog</dt><dd>{_esc((canon_vs.get("aim_catalog") or {}).get("role"))} · {_esc((canon_vs.get("aim_catalog") or {}).get("source"))}</dd>
            <dt>Canonical</dt><dd>{_esc((canon_vs.get("canonical") or {}).get("role"))} · v{_esc((canon_vs.get("canonical") or {}).get("version"))}</dd>
            <dt>Inventory</dt><dd>{_esc((canon_vs.get("inventory") or {}).get("role"))} · {_esc((canon_vs.get("inventory") or {}).get("endpoints"))} endpoints</dd>
            <dt>Runtime profile</dt><dd>{_esc((canon_vs.get("runtime") or {}).get("active_profile"))} · mode {_esc((canon_vs.get("runtime") or {}).get("priority_mode"))}</dd>
          </dl>
        </div>
        """
    )

    # --- 11. Compiled Runtime Routes ---
    html(
        """
        <div class="tf-card">
          <p class="tf-eyebrow">11 · Compiled Runtime Routes</p>
          <h2 class="tf-h2">Active Semantic Router domain routes</h2>
          <p class="tf-sub">Explainable by policy objective overlay + endpoint inventory. Domain→endpoint mapping remains V1 SR.</p>
        </div>
        """
    )
    compiled = pol.get("compiled_routes") or meta.get("routes") or []
    if compiled:
        st.dataframe(
            [
                {
                    "Route": r.get("name"),
                    "Model": r.get("lora_name") or (r.get("endpoint") or {}).get("model"),
                    "Endpoint": r.get("endpoint_ref") or (r.get("endpoint") or {}).get("id"),
                    "Available": r.get("endpoint_available", True),
                    "Hardware": (r.get("endpoint") or {}).get("accelerator")
                    or (r.get("endpoint") or {}).get("hardware"),
                    "Domains": ", ".join(r.get("domains") or []),
                }
                for r in compiled
            ],
            width="stretch",
            hide_index=True,
        )

    # --- 12. Provenance + raw YAML ---
    provenance = pol.get("provenance") or {}
    prov_html = "".join(
        f"<li><strong>{_esc(k)}</strong> — <span class='tf-mono'>{_esc(v)}</span></li>"
        for k, v in provenance.items()
    )
    html(
        f"""
        <div class="tf-card">
          <p class="tf-eyebrow">12 · Provenance</p>
          <h2 class="tf-h2">Where the policy comes from</h2>
          <ul class="tf-sub" style="margin:0.5rem 0 0;padding-left:1.2rem">{prov_html}</ul>
        </div>
        """
    )
    with st.expander("Raw canonical policy YAML", expanded=False):
        try:
            raw = load_canonical_policy()
            # Drop internal keys for display
            display = {k: v for k, v in raw.items() if not str(k).startswith("_")}
            st.code(yaml.dump(display, default_flow_style=False, sort_keys=False, width=96), language="yaml")
        except Exception as exc:
            st.caption(str(exc))
