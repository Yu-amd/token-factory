"""Route Inspector panel — Decision | Policy | Metrics mini-tabs."""

from __future__ import annotations

import html as html_lib
from typing import Any, Callable

import streamlit as st

from components.request_state import RequestState, stream_path_label

HtmlFn = Callable[[str], None]


def _esc(value: Any) -> str:
    return html_lib.escape("" if value is None else str(value))


def _kv_rows(pairs: list[tuple[str, Any]]) -> str:
    rows = []
    for label, value in pairs:
        display = "—" if value is None or value == "" else value
        if isinstance(display, float):
            display = f"{display:.4f}" if display < 1 else f"{display:.3f}"
        rows.append(
            "<div class='tf-pg-kv-row'>"
            f"<dt>{_esc(label)}</dt><dd>{_esc(display)}</dd>"
            "</div>"
        )
    return f"<dl class='tf-pg-kv'>{''.join(rows)}</dl>"


def render_route_inspector(
    state: RequestState,
    *,
    links: dict[str, str],
    html: HtmlFn,
) -> None:
    """Render inspector with live Decision / Policy / Metrics mini-tabs."""
    html(
        """
        <div class="tf-pg-insp-head">
          <span class="tf-pg-insp-title">Route Inspector</span>
        </div>
        """
    )
    tab_dec, tab_pol, tab_met = st.tabs(["Decision", "Policy", "Metrics"])

    with tab_dec:
        conf = state.confidence
        conf_s = f"{conf:.4f}" if isinstance(conf, float) else None
        html(
            _kv_rows(
                [
                    ("Classification", state.classification),
                    ("Confidence", conf_s),
                    ("Route", state.route),
                    ("Domains", ", ".join(state.domains) if state.domains else None),
                    ("Model", state.model),
                    ("Stream path", stream_path_label(state)),
                    ("Finish", state.finish),
                ]
            )
        )
        if state.fallback_reason:
            html(
                f"<p class='tf-pg-insp-note warn'>Fallback: {_esc(state.fallback_reason)}</p>"
            )
        if state.error:
            html(f"<p class='tf-pg-insp-note bad'>Error: {_esc(state.error)}</p>")

    with tab_pol:
        html(
            _kv_rows(
                [
                    ("Profile", state.policy_profile),
                    ("Objective", state.objective),
                    ("Serving", state.serving_pattern),
                    ("Preference", state.preference_label),
                    ("Use case", state.use_case),
                    ("Role", state.role),
                    ("Compute", state.compute),
                    ("Hardware", state.hardware),
                    ("Accelerator", state.accelerator),
                ]
            )
        )
        html(
            "<p class='tf-pg-insp-note'>Values from classify + compiled policy / "
            "matrix metadata — not hard-coded UI recommendations.</p>"
        )

    with tab_met:
        html(
            _kv_rows(
                [
                    ("Classify", f"{state.classify_ms} ms" if state.classify_ms is not None else None),
                    ("TTFT", f"{state.ttft_ms} ms" if state.ttft_ms is not None else None),
                    ("Total", f"{state.total_ms} ms" if state.total_ms is not None else None),
                    ("Path", state.stream_path),
                    ("Gateway buffered", "yes" if state.gateway_buffered else "no" if state.stream_path == "gateway" else "n/a"),
                    ("Fallback", "yes" if state.fallback else "no"),
                    ("Stage", state.stage),
                ]
            )
        )
        g_url = links.get("grafana") or "http://127.0.0.1:3000"
        d_url = links.get("semantic_router_dashboard") or "http://localhost:8700"
        html(
            f"""
            <div class="tf-pg-insp-links">
              <a class="tf-link" href="{_esc(g_url)}" target="_blank" rel="noopener">Grafana</a>
              <a class="tf-link" href="{_esc(d_url)}" target="_blank" rel="noopener">SR Dashboard</a>
            </div>
            """
        )
