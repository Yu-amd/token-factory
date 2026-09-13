"""Automated Demo tab — routing-policy & observability validation (not a benchmark)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def render_automated_demo_tab(
    *,
    meta: dict[str, Any],
    links: dict[str, Any],
    html: Callable[[str], None],
    section: Callable[..., None],
) -> None:
    from token_factory.demo import DemoRunner, list_packs
    from token_factory.demo.persist import list_recent_runs

    section(
        "Automated Demo",
        "Routing-policy & observability validation",
        "Run representative enterprise AI traffic through Token Factory and validate "
        "classification, AMD routing policy, fallback behavior, and observability. "
        "<strong>Not a benchmark</strong> — latency is telemetry only; no comparative "
        "hardware claims.",
        hero=True,
    )

    packs = {p["id"]: p for p in list_packs() if not p.get("error")}
    if not packs:
        st.error("No scenario packs found under demo/scenarios/")
        return

    pack_labels = {
        pid: f"{p.get('display_name', pid)} ({p.get('scenario_count', 0)} scenarios)"
        for pid, p in packs.items()
    }
    life_opts = ["production", "production-preview", "evaluation", "all"]
    traffic_opts = {
        "Sequential": "sequential",
        "Low": "low",
        "Medium": "medium",
        "High": "high",
        "Mixed concurrent": "mixed",
    }

    c1, c2, c3 = st.columns(3)
    with c1:
        pack_label = st.selectbox("Scenario Pack", list(pack_labels.values()), index=0)
        pack_id = next(k for k, v in pack_labels.items() if v == pack_label)
    with c2:
        life = st.selectbox("Lifecycle", life_opts, index=0)
    with c3:
        traffic_label = st.selectbox("Traffic Profile", list(traffic_opts.keys()), index=0)
        traffic = traffic_opts[traffic_label]

    st.markdown("**Failure injection** *(demo runtime overlay only — does not mutate canonical policy)*")
    i1, i2, i3, i4, i5 = st.columns(5)
    with i1:
        inj_pref = st.checkbox("Preferred endpoint unavailable", value=False)
    with i2:
        inj_radeon = st.checkbox("No Radeon", value=False)
    with i3:
        inj_epyc = st.checkbox("No EPYC", value=False)
    with i4:
        inj_local = st.checkbox("No local", value=False)
    with i5:
        inj_life = st.checkbox("Force lifecycle restriction", value=False)

    injections = []
    if inj_pref:
        injections.append("preferred-endpoint-unavailable")
    if inj_radeon:
        injections.append("no-radeon")
    if inj_epyc:
        injections.append("no-epyc")
    if inj_local:
        injections.append("no-local")
    if inj_life:
        injections.append("lifecycle-restriction")

    r1, r2, r3 = st.columns([1, 1, 2])
    with r1:
        seed = st.number_input("Seed (mixed packs)", min_value=0, value=42, step=1)
    with r2:
        req_limit = st.number_input("Max requests", min_value=1, max_value=8000, value=40, step=1)
    with r3:
        force_mock = st.checkbox(
            "Use mock adapters (no cluster)",
            value=True,
            help="Uncheck to use live Gateway/SR when port-forwards are up.",
        )

    pack_meta = packs.get(pack_id) or {}
    if pack_meta.get("description"):
        st.caption(pack_meta["description"][:280])

    run_clicked = st.button("Run Demo", type="primary")

    if "tf_demo_run" not in st.session_state:
        st.session_state.tf_demo_run = None
    if "tf_demo_feed" not in st.session_state:
        st.session_state.tf_demo_feed = []

    if run_clicked:
        feed: list[dict[str, Any]] = []
        progress = st.progress(0.0, text="Starting demo run…")
        current_box = st.empty()
        feed_box = st.empty()

        def on_progress(req: Any, run: Any) -> None:
            total = max(1, len(run.requests))
            done = sum(1 for r in run.requests if r.status in ("completed", "error"))
            progress.progress(min(1.0, done / total), text=f"Request {done}/{total}")
            a = req.actual or {}
            current_box.markdown(
                f"**Current request** · {req.display_name or req.scenario_id}\n\n"
                f"- Classified: `{a.get('classification_category') or a.get('classified_use_case')}`\n"
                f"- Canonical preferred: "
                f"`{(a.get('canonical_preferred') or {}).get('model', '—')} × "
                f"{(a.get('canonical_preferred') or {}).get('compute', '—')}`\n"
                f"- Runtime selected: "
                f"`{a.get('selected_model') or '—'} × {a.get('selected_compute') or '—'}`\n"
                f"- Validation: **{req.overall().value}**"
                + (" · fallback" if a.get("fallback_used") else "")
            )
            feed.append(
                {
                    "status": req.overall().value,
                    "name": req.display_name or req.scenario_id,
                    "model": a.get("selected_model"),
                    "compute": a.get("selected_compute"),
                    "fallback": bool(a.get("fallback_used")),
                }
            )
            lines = []
            for item in feed[-24:]:
                fb = " · fallback" if item["fallback"] else ""
                lines.append(
                    f"`{item['status']}`  {item['name']}  ·  "
                    f"{item['model'] or '—'} / {item['compute'] or '—'}{fb}"
                )
            feed_box.markdown("**Live feed**\n\n" + "\n\n".join(lines))

        with st.spinner("Running Automated Demo…"):
            runner = DemoRunner(mock=True if force_mock else None)
            result = runner.run(
                pack_id,
                lifecycle=life,
                traffic=traffic,
                requests=int(req_limit),
                seed=int(seed),
                inject=injections,
                mock=True if force_mock else None,
                on_progress=on_progress,
            )
        st.session_state.tf_demo_run = result.to_dict()
        st.session_state.tf_demo_feed = feed
        progress.progress(1.0, text="Complete")

    data = st.session_state.tf_demo_run
    if not data:
        st.info("Choose a pack and click **Run Demo** to validate routing policy.")
        _render_history_and_links(links, html, list_recent_runs)
        return

    summary = data.get("validation_summary") or {}
    html(
        f"""
        <div class="tf-card" style="background:#141414;border:1px solid #333;border-radius:0.625rem;
          padding:1.25rem 1.4rem;margin:0.75rem 0 1rem;">
          <p class="tf-eyebrow" style="color:#666;letter-spacing:0.12em;text-transform:uppercase;
            font-size:0.72rem;margin:0 0 0.75rem;">Run summary</p>
          <div style="display:flex;flex-wrap:wrap;gap:1.25rem 2rem;font-size:0.9rem;">
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Pack</div>
              <div style="color:#e8e8e8;font-family:IBM Plex Mono,monospace;">{data.get('scenario_pack')}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Run ID</div>
              <div style="color:#8fd400;font-family:IBM Plex Mono,monospace;font-size:0.78rem;">{data.get('run_id')}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Requests</div>
              <div style="color:#e8e8e8;">{summary.get('completed', 0)} / {summary.get('requests', 0)}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Passed</div>
              <div style="color:#8fd400;">{summary.get('passed', 0)}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Warnings</div>
              <div style="color:#fcd34d;">{summary.get('warnings', 0)}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Failed</div>
              <div style="color:#fca5a5;">{summary.get('failed', 0)}</div></div>
            <div><div style="color:#666;font-size:0.68rem;letter-spacing:0.08em;text-transform:uppercase;">Fallbacks</div>
              <div style="color:#e8e8e8;">{summary.get('fallbacks', 0)}</div></div>
          </div>
          <p style="color:#666;font-size:0.78rem;margin:0.9rem 0 0;">
            Distributions below show routing coverage — not performance comparisons.
          </p>
        </div>
        """
    )

    dist = data.get("distributions") or {}
    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown("**Use-case distribution**")
        st.json(dist.get("use_cases") or {})
    with d2:
        st.markdown("**Compute-family distribution**")
        st.json(dist.get("compute_families") or {})
    with d3:
        st.markdown("**Model distribution**")
        st.json(dist.get("models") or {})

    st.markdown("#### Validation results")
    rows = []
    for r in data.get("requests") or []:
        a = r.get("actual") or {}
        can = a.get("canonical_preferred") or {}
        rows.append(
            {
                "status": _overall_from_validation(r.get("validation") or {}),
                "scenario": r.get("display_name") or r.get("scenario_id"),
                "classified": a.get("classification_category") or a.get("classified_use_case"),
                "canonical": f"{can.get('model', '—')} × {can.get('compute', '—')}",
                "runtime": f"{a.get('selected_model') or '—'} × {a.get('selected_compute') or '—'}",
                "fallback": a.get("fallback_used"),
                "classification": (r.get("validation") or {}).get("classification"),
                "policy": (r.get("validation") or {}).get("policy"),
                "lifecycle": (r.get("validation") or {}).get("lifecycle"),
                "route": (r.get("validation") or {}).get("route"),
                "telemetry": (r.get("validation") or {}).get("telemetry"),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

    with st.expander("Request detail / canonical vs runtime"):
        labels = [
            f"{i+1}. {r.get('display_name') or r.get('scenario_id')}"
            for i, r in enumerate(data.get("requests") or [])
        ]
        if labels:
            pick = st.selectbox("Inspect request", labels)
            detail = (data.get("requests") or [])[labels.index(pick)]
            st.json(
                {
                    "prompt": (detail.get("prompt") or "")[:500],
                    "expected": detail.get("expected"),
                    "actual": {
                        k: detail.get("actual", {}).get(k)
                        for k in (
                            "classification_category",
                            "canonical_preferred",
                            "runtime_selected",
                            "canonical_vs_runtime_reason",
                            "preferred_not_deployed",
                            "fallback_used",
                            "selected_endpoint",
                            "explanation",
                        )
                    },
                    "validation": detail.get("validation"),
                    "telemetry": detail.get("telemetry"),
                }
            )

    _render_history_and_links(links, html, list_recent_runs)


def _overall_from_validation(validation: dict[str, str]) -> str:
    vals = list(validation.values())
    if any(v == "FAIL" for v in vals):
        return "FAIL"
    if any(v == "WARN" for v in vals):
        return "WARN"
    if any(v == "PASS" for v in vals):
        return "PASS"
    return "N/A"


def _render_history_and_links(
    links: dict[str, Any],
    html: Callable[[str], None],
    list_recent_runs: Callable[..., list],
) -> None:
    dash = links.get("semantic_router_dashboard", "http://localhost:8700")
    graf = links.get("grafana", "http://localhost:3000")
    prom = links.get("prometheus", "http://localhost:9090")
    html(
        f"""
        <div class="tf-card" style="background:#141414;border:1px solid #333;border-radius:0.625rem;
          padding:1.25rem 1.4rem;margin:1rem 0;">
          <p class="tf-eyebrow" style="color:#666;letter-spacing:0.12em;text-transform:uppercase;
            font-size:0.72rem;">Observability</p>
          <h3 style="margin:0.35rem 0 0.75rem;color:#e8e8e8;font-size:1.05rem;">Sibling consoles</h3>
          <p style="color:#999;font-size:0.85rem;margin:0 0 0.75rem;">
            Import <span style="font-family:IBM Plex Mono,monospace;color:#8fd400;">
            observability/grafana/token-factory-automated-demo.json</span>
            for the Automated Demo dashboard (definition shipped; live scrape needs Prometheus).
          </p>
          <div class="tf-links">
            <a class="tf-link" href="{graf}" target="_blank" rel="noopener">Open Grafana →</a>
            <a class="tf-link" href="{dash}" target="_blank" rel="noopener">Semantic Router Dashboard →</a>
            <a class="tf-link" href="{prom}" target="_blank" rel="noopener">Open Prometheus →</a>
          </div>
        </div>
        """
    )
    recent = list_recent_runs(8)
    if recent:
        st.markdown("#### Recent runs")
        st.dataframe(
            [
                {
                    "run": (r.get("run_id") or "")[:8],
                    "pack": r.get("scenario_pack"),
                    "started": r.get("started_at"),
                    "passed": (r.get("validation_summary") or {}).get("passed"),
                    "failed": (r.get("validation_summary") or {}).get("failed"),
                    "fallbacks": (r.get("validation_summary") or {}).get("fallbacks"),
                }
                for r in recent
            ],
            width="stretch",
            hide_index=True,
        )
