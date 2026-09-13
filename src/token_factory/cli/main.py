"""Token Factory CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from token_factory.catalog import load_catalog
from token_factory.compiler import compile_all
from token_factory.config import (
    ConfigValidationError,
    load_endpoints,
    load_policies,
    load_token_factory,
    validate_all,
)
from token_factory.runtime.paths import repo_root
from token_factory.runtime.port_forward import (
    dashboard_deployment_ready,
    find_available_local_port,
    list_forwards,
    resolve_dashboard_service,
    start_dashboard_forward,
    start_forwards,
    stop_all,
)
from token_factory.version import PINNED_VERSIONS, VIRTUAL_MODEL

app = typer.Typer(name="token-factory", help="AMD Token Factory reference architecture CLI")
policy_app = typer.Typer(help="AMD Canonical Routing Policy commands")
demo_app = typer.Typer(
    help="Automated Demo — routing-policy & observability validation (not a benchmark)"
)
app.add_typer(policy_app, name="policy")
app.add_typer(demo_app, name="demo")
console = Console()


def _probe(url: str, path: str) -> str:
    try:
        r = httpx.get(f"{url.rstrip('/')}{path}", timeout=3.0, follow_redirects=True)
        return "ok" if r.status_code < 400 else f"HTTP {r.status_code}"
    except Exception as exc:
        return f"unreachable ({exc.__class__.__name__})"


@app.command()
def status() -> None:
    """Check health of stack components."""
    gateway = os.environ.get("TF_GATEWAY_URL", "http://127.0.0.1:18080")
    sr_api = os.environ.get("TF_SR_URL", "http://127.0.0.1:8081")
    dashboard = os.environ.get("TF_SR_DASHBOARD_URL", "http://localhost:8700")
    grafana = os.environ.get("TF_GRAFANA_URL", "http://localhost:3000")
    prometheus = os.environ.get("TF_PROMETHEUS_URL", "http://localhost:9090")

    probes = [
        ("AI Gateway", gateway, "/v1/models"),
        ("Semantic Router API", sr_api, "/health"),
        ("SR Dashboard", dashboard, "/"),
        ("Grafana", grafana, "/api/health"),
        ("Prometheus", prometheus, "/-/healthy"),
    ]
    table = Table(title="Token Factory Status")
    table.add_column("Component")
    table.add_column("URL")
    table.add_column("Health")
    for name, url, path in probes:
        table.add_row(name, url, _probe(url, path))
    console.print(table)


@app.command()
def dashboard() -> None:
    """Discover SR dashboard, port-forward, and verify HTTP access."""
    svc_name, remote_port = resolve_dashboard_service()
    deploy_ok, deploy_msg = dashboard_deployment_ready()

    try:
        local_port, port_note = find_available_local_port(8700)
    except RuntimeError as exc:
        console.print(f"[red]ERROR:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not deploy_ok:
        console.print(f"[yellow]WARN:[/yellow] {deploy_msg}")

    entry = start_dashboard_forward(preferred_port=local_port)
    url = f"http://localhost:{entry['local_port']}"

    curl_ok = False
    curl_detail = ""
    for attempt in range(5):
        try:
            result = subprocess.run(
                ["curl", "-sf", f"{url}/"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            curl_ok = result.returncode == 0
            curl_detail = "curl -f / succeeded" if curl_ok else result.stderr.strip() or "curl failed"
            if curl_ok:
                break
        except (subprocess.SubprocessError, FileNotFoundError):
            try:
                r = httpx.get(f"{url}/", timeout=5.0, follow_redirects=True)
                curl_ok = r.status_code < 400
                curl_detail = f"HTTP {r.status_code}"
                if curl_ok:
                    break
            except Exception as exc:
                curl_detail = str(exc)
        time.sleep(0.5)

    status_lines = [
        f"Service:      {svc_name} (ns vllm-semantic-router-system:{remote_port})",
        f"Deployment:   {'healthy' if deploy_ok else 'NOT READY'} — {deploy_msg}",
        f"Local URL:    {url}",
        f"Port-forward: pid {entry.get('pid')} (tracked)",
        f"HTTP probe:   {'OK' if curl_ok else 'FAILED'} — {curl_detail}",
    ]
    if port_note := entry.get("port_note"):
        status_lines.insert(3, f"Port note:    {port_note}")

    console.print(
        Panel(
            "\n".join(status_lines),
            title="Semantic Router Dashboard",
            border_style="green" if curl_ok else "yellow",
        )
    )

    if not curl_ok:
        console.print("[red]Dashboard port-forward up but HTTP probe failed.[/red]")
        raise typer.Exit(1)

    console.print(f"\nOpen: [bold cyan]{url}[/bold cyan]")


@app.command()
def grafana() -> None:
    """Show Grafana URL."""
    url = os.environ.get("TF_GRAFANA_URL", "http://localhost:3000")
    console.print(f"Grafana: {url} (default credentials admin/admin)")


ports_app = typer.Typer(help="Manage kubectl port-forwards")
app.add_typer(ports_app, name="ports")


@ports_app.command("start")
def ports_start() -> None:
    """Start tracked port-forwards."""
    started = start_forwards()
    for entry in started:
        console.print(
            f"Started {entry['name']}: localhost:{entry['local_port']} "
            f"(pid {entry['pid']}, svc {entry['service']})"
        )


@ports_app.command("stop")
def ports_stop() -> None:
    """Stop all tracked port-forwards."""
    count = stop_all()
    console.print(f"Stopped {count} port-forward(s)")


@ports_app.command("list")
def ports_list() -> None:
    """List port-forward state."""
    forwards = list_forwards()
    if not forwards:
        console.print("No port-forwards tracked.")
        return
    table = Table(title="Port Forwards")
    table.add_column("Name")
    table.add_column("Local")
    table.add_column("Service")
    table.add_column("PID")
    table.add_column("Alive")
    for entry in forwards:
        table.add_row(
            entry["name"],
            str(entry["local_port"]),
            f"{entry['namespace']}/{entry['service']}",
            str(entry.get("pid", "")),
            "yes" if entry.get("alive") else "no",
        )
    console.print(table)


@app.command()
def preflight() -> None:
    """Validate toolchain and configuration."""
    errors: list[str] = []
    for cmd in ("kubectl", "helm", "python3"):
        if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
            errors.append(f"Missing required command: {cmd}")

    try:
        endpoints = load_endpoints()
        policies = load_policies()
        token_factory = load_token_factory()
        catalog = load_catalog()
        validate_all(endpoints, policies, token_factory, catalog)
        console.print("[green]Configuration valid[/green]")
    except (ConfigValidationError, FileNotFoundError, ValueError) as exc:
        errors.append(str(exc))

    if errors:
        for err in errors:
            console.print(f"[red]ERROR:[/red] {err}")
        raise typer.Exit(1)
    console.print("[green]Preflight passed[/green]")


@app.command()
def install(
    mock_backends: bool = typer.Option(False, help="Deploy mock OpenAI backends"),
    skip_observability: bool = typer.Option(False, help="Skip Prometheus/Grafana"),
) -> None:
    """Install stack via modular scripts."""
    root = repo_root()
    args = []
    if mock_backends:
        args.append("--mock-backends")
    if skip_observability:
        args.append("--skip-observability")
    script = root / "scripts" / "install-all.sh"
    cmd = ["bash", str(script), *args]
    console.print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


@app.command()
def apply() -> None:
    """Compile config and apply generated manifests."""
    compile_cmd()
    root = repo_root()
    subprocess.run(["bash", str(root / "scripts" / "apply-generated.sh")], check=True)


@app.command("compile")
def compile_cmd(
    endpoints_file: Path | None = typer.Option(None, "--endpoints"),
    policies_file: Path | None = typer.Option(None, "--policies"),
    config_file: Path | None = typer.Option(None, "--config"),
) -> None:
    """Compile endpoints + policies into generated/ artifacts."""
    endpoints = load_endpoints(endpoints_file)
    policies = load_policies(policies_file)
    token_factory = load_token_factory(config_file)
    catalog = load_catalog()
    outputs = compile_all(endpoints, policies, token_factory, catalog)
    for name, path in outputs.items():
        console.print(f"Wrote {name}: {path}")


@app.command()
def verify() -> None:
    """Verify deployed resources."""
    checks = [
        ("deployment", "envoy-gateway-system", "envoy-gateway"),
        ("deployment", "envoy-ai-gateway-system", "ai-gateway-controller"),
        ("deployment", "vllm-semantic-router-system", "semantic-router"),
        ("deployment", "vllm-semantic-router-system", "semantic-router-dashboard"),
    ]
    failed = 0
    for kind, ns, name in checks:
        result = subprocess.run(
            ["kubectl", "get", kind, name, "-n", ns],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            console.print(f"[red]MISSING[/red] {ns}/{name}")
            failed += 1
        else:
            console.print(f"[green]OK[/green] {ns}/{name}")
    if failed:
        raise typer.Exit(1)


@app.command()
def uninstall() -> None:
    """Uninstall stack components."""
    root = repo_root()
    subprocess.run(["bash", str(root / "scripts" / "uninstall-all.sh")], check=True)
    stop_all()


@app.command("route-explain")
def route_explain(
    text: str = typer.Argument(..., help="User query to classify"),
    policies_file: Path | None = typer.Option(None, "--policies"),
) -> None:
    """Explain routing decision for sample text (domain heuristic)."""
    policies = load_policies(policies_file)
    routes = sorted(
        policies.get("policy", {}).get("routes", []),
        key=lambda r: r.get("priority", 0),
        reverse=True,
    )
    lowered = text.lower()
    matched = None
    for route in routes:
        for domain in route.get("domains", []):
            if domain.lower() in lowered or domain.replace(" ", "") in lowered.replace(" ", ""):
                matched = route
                break
        if matched:
            break
    if not matched and routes:
        matched = routes[-1]
    if matched:
        console.print(
            json.dumps(
                {
                    "matched_route": matched.get("name"),
                    "lora_name": matched.get("lora_name") or matched.get("name"),
                    "endpoint_ref": matched.get("endpoint_ref"),
                    "virtual_model": policies.get("policy", {}).get(
                        "virtual_model", VIRTUAL_MODEL
                    ),
                },
                indent=2,
            )
        )
    else:
        console.print("No route matched")


@app.command("catalog-update")
def catalog_update(
    output: Path | None = typer.Option(None, help="Output path (default catalog/aims.yaml)"),
) -> None:
    """Refresh AIM catalog metadata header (manual matrix update required)."""
    path = output or (repo_root() / "catalog" / "aims.yaml")
    data = load_catalog(path)
    data.setdefault("metadata", {})["last_refreshed"] = datetime.now(timezone.utc).isoformat()
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    console.print(f"Updated catalog metadata at {path}")


catalog_app = typer.Typer(help="AIM catalog inspection / audit")
app.add_typer(catalog_app, name="catalog")


@catalog_app.command("audit")
def catalog_audit(
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
) -> None:
    """Audit merged AIM catalog counts and soft gaps vs pinned AMD docs snapshot."""
    from token_factory.routing_matrix import audit_catalog

    result = audit_catalog()
    if json_out:
        console.print_json(data=result)
        return
    console.print(
        Panel.fit(
            f"[bold]AIM Catalog Audit[/bold]\n"
            f"GA aims.yaml          {result['ga_aims']}\n"
            f"MI350P Tech Preview   {result['tech_preview_mi350p_models']}\n"
            f"Merged catalog        {result['merged_catalog_models']}\n"
            f"models.yaml           {result['models_yaml']}\n"
            f"Compute columns       {result['compute_columns']}\n"
            f"Aliases               {result['aliases']}\n"
            f"AMD docs (pinned)     {result['amd_docs_url']}\n"
            f"Reconcile             snapshot only — no runtime scrape"
        )
    )
    table = Table(title="Vendors")
    table.add_column("Vendor")
    table.add_column("Models", justify="right")
    for vendor, n in (result.get("vendors") or {}).items():
        table.add_row(vendor, str(n))
    console.print(table)
    gaps = result.get("soft_gaps") or []
    if gaps:
        console.print("\n[bold yellow]Soft gaps[/bold yellow]")
        for g in gaps:
            models = g.get("models") or []
            console.print(f"  • {g.get('kind')}: {g.get('note')}")
            for m in models[:12]:
                console.print(f"      - {m}")
            if len(models) > 12:
                console.print(f"      … +{len(models) - 12} more")
    else:
        console.print("\n[green]No soft gaps recorded.[/green]")


matrix_app = typer.Typer(help="Portfolio / Executive matrix commands")
app.add_typer(matrix_app, name="matrix")

evidence_app = typer.Typer(help="Evidence catalog audit / gap analysis")
app.add_typer(evidence_app, name="evidence")


@evidence_app.command("audit")
def evidence_audit_cmd(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Audit model provenance + evidence catalog coverage."""
    from token_factory.routing_matrix import RecommendationEngine, load_routing_bundle

    result = RecommendationEngine(load_routing_bundle()).evidence_audit()
    if json_out:
        console.print_json(data=result)
        return
    gaps = result.get("gaps") or {}
    console.print(
        Panel.fit(
            f"[bold]Evidence Audit[/bold] · policy {result.get('policy_version')}\n"
            f"Models {result.get('model_count')} · records {result.get('evidence_records')}\n"
            f"AMD measurements {result.get('amd_measurements')!r}\n"
            f"Verified models {len(result.get('verified_models') or [])}\n"
            f"Gaps {gaps.get('gap_count', 0)}"
        )
    )
    console.print(f"[dim]{result.get('statement')}[/dim]")
    soft = [
        g
        for g in (gaps.get("gaps") or [])
        if g.get("gap") == "amd_performance_evidence_pending"
    ][:8]
    if soft:
        console.print("\n[bold]Soft gaps (AMD measured pending):[/bold]")
        for g in soft:
            console.print(f"  • {g.get('model')} [{g.get('maturity')}/{g.get('review_status')}]")


@evidence_app.command("gaps")
def evidence_gaps_cmd(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List evidence gaps (pending AMD measured, missing sources, unknown caps)."""
    from token_factory.routing_matrix import RecommendationEngine, load_routing_bundle

    result = RecommendationEngine(load_routing_bundle()).evidence_gaps()
    if json_out:
        console.print_json(data=result)
        return
    console.print(
        Panel.fit(
            f"[bold]Evidence Gaps[/bold]\n"
            f"Count {result.get('gap_count')} · records {result.get('record_count')}\n"
            f"amd_measurements_present={result.get('amd_measurements_present')}"
        )
    )
    by_type: dict[str, int] = {}
    for g in result.get("gaps") or []:
        by_type[g.get("gap", "?")] = by_type.get(g.get("gap", "?"), 0) + 1
    table = Table(title="Gap types")
    table.add_column("Gap")
    table.add_column("Count", justify="right")
    for k, v in sorted(by_type.items(), key=lambda kv: -kv[1]):
        table.add_row(k, str(v))
    console.print(table)


@matrix_app.command("audit")
def matrix_audit(
    use_case: str = typer.Option(
        "coding-assistant", "--use-case", "-u", help="Use-case id"
    ),
    view_mode: str = typer.Option(
        "portfolio", "--view", help="portfolio|executive"
    ),
    show: str = typer.Option("all", "--show", help="all|suitable|recommended|deployed|preview-tp"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Audit Portfolio/Executive matrix coverage (real row/column counts)."""
    from token_factory.routing_matrix import audit_matrix

    result = audit_matrix(use_case, view_mode=view_mode, show=show)
    if json_out:
        console.print_json(data=result)
        return
    cc = result.get("catalog_counts") or {}
    console.print(
        Panel.fit(
            f"[bold]Matrix Audit · {result.get('view_mode')}[/bold]\n"
            f"Use case       {result['use_case']}\n"
            f"Catalog models {result['catalog_models']}\n"
            f"rows           {result['rows']} (full catalog)\n"
            f"display_rows   {result['display_rows']}\n"
            f"Columns        {', '.join(result.get('columns') or [])}\n"
            f"AIM cells      {result.get('cells_with_aim_support')}\n"
            f"Dash (—) cells {result.get('cells_dash_no_support')}\n"
            f"Suitable       {cc.get('suitable')} · Recommended {cc.get('recommended')} · "
            f"Deployed {cc.get('deployed')} · Preview/TP {cc.get('preview_tp')}"
        )
    )
    if result.get("coverage_warning"):
        console.print(f"[yellow]{result['coverage_warning']}[/yellow]")
    statuses = result.get("row_status_counts") or {}
    if statuses:
        table = Table(title="Row status")
        table.add_column("Status")
        table.add_column("Count", justify="right")
        for status, n in statuses.items():
            table.add_row(status, str(n))
        console.print(table)


@app.command()
def recommend(
    use_case: str | None = typer.Option(
        None, "--use-case", "-u", help="Enterprise use-case id (e.g. coding-assistant)"
    ),
    objective: str | None = typer.Option(
        None,
        "--objective",
        "-o",
        help="balanced|token-cost|lowest-cost-sufficient|quality|latency|throughput|edge-local|enterprise",
    ),
    compute: str | None = typer.Option(
        None, "--compute", "-c", help="Invert: recommend workloads for this accelerator/family"
    ),
    utilization: str = typer.Option("medium", help="low|medium|high"),
    lifecycle: str = typer.Option(
        "production",
        "--lifecycle",
        "-L",
        help="production|production-preview|evaluation|all",
    ),
    serving_pattern: str | None = typer.Option(
        None,
        "--serving-pattern",
        "-S",
        help="interactive|online-throughput|batch|offline-batch",
    ),
    data_locality: bool = typer.Option(
        False, "--data-locality", help="Prefer local/privacy-capable compute (Radeon)"
    ),
    simulate: bool = typer.Option(False, "--simulate", help="Show runtime selection vs inventory"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    list_use_cases: bool = typer.Option(False, "--list-use-cases", help="List use-case ids"),
) -> None:
    """AMD Opinionated Routing recommendations (SHOULD RUN + live inventory)."""
    from token_factory.routing_matrix import RecommendationEngine

    engine = RecommendationEngine()
    if list_use_cases:
        for uc in engine.list_use_cases():
            console.print(f"{uc['id']:28} {uc.get('category',''):12} {uc['display_name']}")
        return

    endpoints = load_endpoints().get("endpoints", [])

    if compute and not use_case:
        result = engine.recommend_for_compute(
            compute,
            objective=objective or "balanced",
            endpoints=endpoints,
            lifecycle_mode=lifecycle,
        )
        if json_out:
            console.print_json(data=result)
            return
        console.print(
            Panel.fit(
                f"[bold]Compute[/bold] {compute}\n[bold]Objective[/bold] {result['objective']}\n"
                f"[bold]Lifecycle[/bold] {result.get('lifecycle_mode')}\n"
                f"[dim]policy {result.get('policy_version')}[/dim]"
            )
        )
        for block in result["use_cases"][:12]:
            console.print(f"\n[cyan]{block['use_case']['display_name']}[/cyan] ({block['use_case']['id']})")
            for row in block["top"]:
                console.print(
                    f"  {row.get('rank') or '-':>2}  {row['model']:<42} {row['compute']:<10} "
                    f"{row['aim_support']:<10} {row.get('lifecycle',''):<12} {row['recommendation']}"
                )
        return

    if not use_case:
        console.print("[red]Provide --use-case or --compute (or --list-use-cases)[/red]")
        raise typer.Exit(2)

    if simulate:
        result = engine.simulate_route(
            use_case,
            objective=objective,
            utilization=utilization,
            endpoints=endpoints,
            lifecycle_mode=lifecycle,
            data_locality=data_locality,
            serving_pattern=serving_pattern,
        )
    else:
        result = engine.recommend(
            use_case,
            objective=objective,
            utilization=utilization,
            endpoints=endpoints,
            lifecycle_mode=lifecycle,
            data_locality=data_locality,
            serving_pattern=serving_pattern,
        )

    if json_out:
        console.print_json(data=result)
        return

    title = "AMD TOKEN FACTORY RECOMMENDATION" + (" (SIMULATE)" if simulate else "")
    console.print(
        Panel.fit(
            f"[bold]{title}[/bold]\n"
            f"Use Case   {result['use_case']['display_name']} ({result['use_case']['id']})\n"
            f"Objective  {result['objective']}\n"
            f"Serving    {result.get('serving_pattern')} · latency {result.get('latency_requirement')}\n"
            f"Lifecycle  {result.get('lifecycle_mode')} · allow {result.get('allowed_lifecycles')}\n"
            f"Cost data  {result.get('cost_data', 'relative')} · evidence {result.get('cost_evidence_default', 'RELATIVE')} · policy {result.get('policy_version')}"
        )
    )
    if result.get("locality_note"):
        console.print(f"[yellow]{result['locality_note']}[/yellow]")

    rows = result.get("amd_recommendation") if simulate else result.get("ranked") or result.get("candidates")
    table = Table(title="Ranked candidates")
    table.add_column("Rank")
    table.add_column("Model")
    table.add_column("Compute")
    table.add_column("AIM")
    table.add_column("Life")
    table.add_column("Rec")
    table.add_column("Live")
    for row in (rows or [])[:15]:
        table.add_row(
            str(row.get("rank") or "—"),
            row["model"],
            row["compute"],
            row.get("aim_support", ""),
            row.get("lifecycle", ""),
            row.get("recommendation", ""),
            "yes" if row.get("endpoint_available") else "",
        )
    console.print(table)

    if simulate:
        sel = result.get("selected_runtime_route")
        console.print(f"\n[bold]Selected runtime route:[/bold] {sel or 'none'}")
        console.print(f"[dim]{result.get('explanation')}[/dim]")
        excl = result.get("lifecycle_exclusions") or []
        if excl:
            console.print(f"\n[bold]Lifecycle exclusions ({len(excl)}):[/bold]")
            for e in excl[:6]:
                console.print(
                    f"  • {e['model']} × {e['compute']} [{e.get('lifecycle')}] — {e.get('exclusion_reason')}"
                )
        sp_excl = result.get("serving_pattern_exclusions") or []
        if sp_excl:
            console.print(f"\n[bold]Serving-pattern / latency notes ({len(sp_excl)}):[/bold]")
            for e in sp_excl[:4]:
                console.print(f"  • {e['model']} × {e['compute']}")
        loc_excl = result.get("locality_exclusions") or []
        if loc_excl:
            console.print(f"\n[bold]Locality soft-exclusions ({len(loc_excl)}):[/bold]")
            for e in loc_excl[:4]:
                console.print(f"  • {e.get('model')} × {e.get('compute')}")
        deployed = result.get("currently_deployed_eligible") or []
        if deployed:
            console.print("\n[bold]Currently deployed eligible:[/bold]")
            for d in deployed[:5]:
                console.print(f"  • {d['model']} × {d['compute']} ({d.get('endpoint_id')})")


@policy_app.command("audit")
def policy_audit_cmd(
    use_case: str | None = typer.Option(
        None, "--use-case", "-u", help="Optional use-case id (default: coding family sample)"
    ),
    lifecycle_mode: str = typer.Option("production", "--lifecycle", "-L"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Flag Preferred + low evidence / specialization-only style wins."""
    from token_factory.routing_matrix import RecommendationEngine, load_routing_bundle

    result = RecommendationEngine(load_routing_bundle()).policy_audit(
        use_case_id=use_case, lifecycle_mode=lifecycle_mode
    )
    if json_out:
        console.print_json(data=result)
        return
    console.print(
        Panel.fit(
            f"[bold]Policy Audit[/bold] · v{result.get('policy_version')}\n"
            f"Findings {result.get('finding_count')}"
        )
    )
    for f in (result.get("findings") or [])[:20]:
        console.print(
            f"  • {f.get('use_case')}: {f.get('model')} × {f.get('compute')} "
            f"[{f.get('recommendation')} · {f.get('confidence')} · {f.get('evidence_badge')}]"
        )
        for issue in f.get("issues") or []:
            console.print(f"      - {issue}")
    if not result.get("findings"):
        console.print("[green]No Preferred/low-evidence findings in sample.[/green]")


@policy_app.command("compare")
def policy_compare_cmd(
    use_case: str = typer.Option(..., "--use-case", "-u", help="Use-case id"),
    model_a: str = typer.Option(..., "--model-a", help="First model id"),
    model_b: str = typer.Option(..., "--model-b", help="Second model id"),
    compute: str | None = typer.Option(None, "--compute", "-c", help="Compute id e.g. MI355X"),
    objective: str | None = typer.Option(None, "--objective", "-o"),
    lifecycle_mode: str = typer.Option("production", "--lifecycle", "-L"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Explainable model-vs-model policy comparison (not a benchmark winner)."""
    from token_factory.routing_matrix import RecommendationEngine, load_routing_bundle

    result = RecommendationEngine(load_routing_bundle()).compare_models(
        use_case,
        model_a,
        model_b,
        compute_id=compute,
        objective=objective,
        lifecycle_mode=lifecycle_mode,
    )
    if json_out:
        console.print_json(data=result)
        return
    pref = result.get("policy_preference") or {}
    console.print(
        Panel.fit(
            f"[bold]Policy Compare[/bold] · {use_case}"
            + (f" · {compute}" if compute else "")
            + f"\nv{result.get('policy_version')} · objective {result.get('objective')}\n"
            f"{model_a} vs {model_b}"
        )
    )
    dims = result.get("dimensions") or {}
    table = Table(title="Capability / strength dimensions")
    table.add_column("Dimension")
    table.add_column(model_a.split("/")[-1])
    table.add_column(model_b.split("/")[-1])
    for name, row in dims.items():
        table.add_row(name, str(row.get(model_a)), str(row.get(model_b)))
    console.print(table)
    aim = result.get("aim_support") or {}
    amd = result.get("amd_performance_evidence") or {}
    console.print(
        f"AIM support: {model_a.split('/')[-1]}={aim.get(model_a)} · "
        f"{model_b.split('/')[-1]}={aim.get(model_b)}"
    )
    console.print(
        f"AMD performance evidence: {amd.get(model_a)} · {amd.get(model_b)}"
    )
    if pref:
        console.print(
            f"\nPolicy preference (not a benchmark win): {pref.get('model')} · "
            f"{pref.get('recommendation')} · confidence {pref.get('confidence')}"
        )
    if result.get("why_a_over_b"):
        console.print(f"\nWhy {model_a.split('/')[-1]} over {model_b.split('/')[-1]}:")
        for line in result["why_a_over_b"]:
            console.print(f"  • {line}")
    if result.get("why_b_over_a"):
        console.print(f"\nWhy {model_b.split('/')[-1]} over {model_a.split('/')[-1]}:")
        for line in result["why_b_over_a"]:
            console.print(f"  • {line}")
    console.print(f"\n[yellow]Caveat:[/yellow] {result.get('caveat')}")


@policy_app.command("validate")
def policy_validate(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Validate canonical AMD routing policy + profile overlays."""
    from token_factory.policy import (
        list_profiles,
        load_canonical_policy,
        load_profile,
        validate_canonical_policy,
    )
    from token_factory.policy.schema import validate_profile_overlay
    from token_factory.routing_matrix.loader import load_routing_bundle

    bundle = load_routing_bundle()
    policy = load_canonical_policy()
    use_case_ids = {u["id"] for u in bundle["use_cases"].get("use_cases") or []}
    compute_ids = {c["id"] for c in bundle["compute"].get("compute") or []}
    errors = validate_canonical_policy(
        policy,
        use_case_ids=use_case_ids,
        compute_ids=compute_ids,
        strict=False,
    )
    for p in list_profiles():
        errors.extend(
            [f"profile {p['id']}: {e}" for e in validate_profile_overlay(load_profile(p["id"]))]
        )
    payload = {
        "ok": not errors,
        "source": policy.get("_source_path"),
        "version": (policy.get("metadata") or {}).get("amd_routing_policy", {}).get("version"),
        "errors": errors,
    }
    if json_out:
        console.print_json(data=payload)
        if errors:
            raise typer.Exit(1)
        return
    if errors:
        for err in errors:
            console.print(f"[red]ERROR:[/red] {err}")
        raise typer.Exit(1)
    console.print(
        f"[green]Policy valid[/green] · {payload['source']} · v{payload['version']}"
    )


@policy_app.command("show")
def policy_show(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show high-level canonical policy metadata."""
    from token_factory.policy import list_profiles, load_canonical_policy, policy_ui_metadata

    policy = load_canonical_policy()
    meta = policy_ui_metadata()
    nested = policy.get("_canonical") or policy.get("policy") or {}
    payload = {
        "id": meta.get("id"),
        "display_name": meta.get("display_name"),
        "version": meta.get("version"),
        "published": meta.get("published"),
        "source_path": meta.get("source_path"),
        "active_profile": meta.get("active_profile"),
        "virtual_model": meta.get("virtual_model"),
        "counts": meta.get("counts"),
        "inputs": nested.get("inputs") if isinstance(nested, dict) else meta.get("inputs"),
        "profiles": [p["id"] for p in list_profiles()],
        "decision_pipeline": meta.get("decision_pipeline"),
    }
    if json_out:
        console.print_json(data=payload)
        return
    console.print(
        Panel.fit(
            f"[bold]{payload['display_name']}[/bold]\n"
            f"Version  {payload['version']} · published {payload['published']}\n"
            f"Source   {payload['source_path']}\n"
            f"Profile  {payload['active_profile']} · virtual {payload['virtual_model']}"
        )
    )
    counts = payload.get("counts") or {}
    table = Table(title="Counts")
    table.add_column("Metric")
    table.add_column("Value")
    for k, v in counts.items():
        table.add_row(k, str(v))
    console.print(table)


@policy_app.command("explain")
def policy_explain(
    use_case: str = typer.Option(..., "--use-case", "-u"),
    objective: str | None = typer.Option(None, "--objective", "-o"),
    serving_pattern: str | None = typer.Option(None, "--serving-pattern", "-S"),
    traffic: str = typer.Option("medium", "--traffic", "-t"),
    lifecycle: str = typer.Option("production", "--lifecycle", "-L"),
    deployment: str | None = typer.Option(None, "--deployment"),
    data_locality: bool = typer.Option(False, "--data-locality"),
    profile: str | None = typer.Option(None, "--profile"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Explain Policy — seven steps from the canonical recommendation engine."""
    from token_factory.policy import explain_policy

    result = explain_policy(
        use_case,
        objective=objective,
        serving_pattern=serving_pattern,
        traffic=traffic,
        lifecycle=lifecycle,
        deployment=deployment,
        data_locality=data_locality,
        profile=profile,
    )
    if json_out:
        console.print_json(data=result)
        return
    console.print(
        Panel.fit(
            f"[bold]EXPLAIN POLICY[/bold] · v{result.get('policy_version')}\n"
            f"Use case   {result['use_case']['display_name']} ({result['use_case']['id']})\n"
            f"Objective  {result['objective']} · serving {result['serving_pattern']}\n"
            f"Traffic    {result['traffic']} · lifecycle {result['lifecycle_mode']}"
        )
    )
    for step in result.get("steps") or []:
        console.print(f"\n[cyan]Step {step['step']} — {step['title']}[/cyan]")
        if step["step"] == 1:
            console.print(f"  required: {step.get('required')} · floor: {step.get('capability_floor')}")
        elif step["step"] == 2:
            console.print(
                f"  lifecycle={step.get('lifecycle_mode')} allow={step.get('allowed_lifecycles')} "
                f"exclusions={step.get('lifecycle_exclusions')}"
            )
        elif step["step"] == 3:
            for note in (step.get("notes") or [])[:3]:
                console.print(f"  • {note[:140]}")
        elif step["step"] == 4:
            console.print(f"  objective={step.get('objective')} · label={step.get('preference_label')}")
        elif step["step"] == 5:
            for c in (step.get("candidates") or [])[:5]:
                console.print(
                    f"  {c.get('rank') or '-':>2}  {c['model']:<42} {c['compute']:<10} {c['recommendation']}"
                )
        elif step["step"] == 6:
            sel = step.get("selected_runtime_route")
            console.print(f"  selected: {sel or 'none'}")
            console.print(f"  [dim]{step.get('explanation')}[/dim]")
        elif step["step"] == 7:
            for rule in (step.get("canonical_rules") or [])[:4]:
                console.print(f"  • {rule}")
            chain = step.get("profile_fallback_chain") or []
            if chain:
                console.print(f"  V1 chain: {' → '.join(chain)}")


@policy_app.command("coverage")
def policy_coverage_cmd(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Show use-case policy coverage and explicit gaps."""
    from token_factory.policy import policy_coverage

    result = policy_coverage()
    if json_out:
        console.print_json(data=result)
        return
    counts = result["counts"]
    console.print(
        Panel.fit(
            f"[bold]AMD ROUTING POLICY {result.get('policy_version')}[/bold]\n"
            f"Use cases             {counts['use_cases']}\n"
            f"Objectives            {counts['objectives']}\n"
            f"Serving patterns      {counts['serving_patterns']}\n"
            f"Compute targets       {counts['compute_targets']}\n"
            f"Lifecycle modes       {counts['lifecycle_modes']}\n"
            f"GA-capable            {counts['ga_capable']}\n"
            f"Preview-only          {counts['preview_only']}\n"
            f"Tech-preview-only     {counts['tech_preview_only']}\n"
            f"No eligible candidate {counts['no_eligible_candidate']}"
        )
    )
    gaps = result.get("gaps") or []
    if gaps:
        console.print("\n[bold]Gaps[/bold]")
        for g in gaps:
            console.print(f"  • {g['use_case']}: {g['reason']}")


@policy_app.command("compile")
def policy_compile_cmd(
    profile: str | None = typer.Option(None, "--profile"),
    use_case: str | None = typer.Option(None, "--use-case", "-u"),
    objective: str | None = typer.Option(None, "--objective", "-o"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compile effective policy (+ optional ranked candidates) from canonical + profile."""
    from token_factory.policy import compile_effective_policy

    result = compile_effective_policy(
        profile_name=profile, use_case=use_case, objective=objective
    )
    if json_out:
        console.print_json(data=result)
        return
    meta = result["effective_policy"]
    console.print(
        Panel.fit(
            f"[bold]Effective policy[/bold] v{meta.get('version')}\n"
            f"Profile {meta.get('active_profile')} · routes {len(meta.get('compiled_routes') or [])}"
        )
    )
    ranked = result.get("ranked_candidates")
    if ranked:
        for c in (ranked.get("ranked") or [])[:8]:
            console.print(
                f"  {c.get('rank') or '-':>2}  {c['model']:<42} {c['compute']:<10} {c['recommendation']}"
            )


@policy_app.command("export")
def policy_export(
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Export canonical policy + UI metadata as JSON."""
    from token_factory.policy import load_canonical_policy, policy_ui_metadata

    payload = {
        "canonical": load_canonical_policy(),
        "ui": policy_ui_metadata(),
    }
    # Strip non-serializable path objects if any
    text = json.dumps(payload, indent=2, default=str)
    if output:
        output.write_text(text, encoding="utf-8")
        console.print(f"Wrote {output}")
    else:
        console.print(text)


@policy_app.command("diff")
def policy_diff(
    left: str = typer.Option("amd-balanced", "--left"),
    right: str = typer.Option("amd-enterprise", "--right"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Compare two profile overlays (objective / lifecycle / fallback — not full matrices)."""
    from token_factory.policy import load_profile

    def _summary(name: str) -> dict[str, Any]:
        doc = load_profile(name)
        policy = doc.get("policy") or {}
        overlay = doc.get("overlay") or policy.get("overlay") or {}
        return {
            "name": policy.get("name", name),
            "priority_mode": policy.get("priority_mode"),
            "objective": overlay.get("objective"),
            "lifecycle_strictness": overlay.get("lifecycle_strictness"),
            "economic_preference": overlay.get("economic_preference"),
            "locality_preference": overlay.get("locality_preference"),
            "fallback_chain": (policy.get("fallback") or {}).get("chain"),
            "route_count": len(policy.get("routes") or []),
        }

    a, b = _summary(left), _summary(right)
    payload = {"left": a, "right": b, "changed": {k: [a.get(k), b.get(k)] for k in a if a.get(k) != b.get(k)}}
    if json_out:
        console.print_json(data=payload)
        return
    table = Table(title=f"Profile diff: {left} vs {right}")
    table.add_column("Field")
    table.add_column(left)
    table.add_column(right)
    for k in a:
        table.add_row(k, str(a.get(k)), str(b.get(k)))
    console.print(table)


@app.command()
def ui() -> None:
    """Launch Streamlit UI locally."""
    ui_dir = repo_root() / "ui"
    # Run from ui/ so .streamlit/config.toml (dark SR-aligned theme) is applied.
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py"],
        cwd=str(ui_dir),
        check=False,
    )


@demo_app.command("plan")
def demo_plan(
    pack: str = typer.Option("smoke", "--pack", "-p", help="Scenario pack id"),
    seed: int | None = typer.Option(None, "--seed", help="Seed for mixed packs"),
    requests: int | None = typer.Option(
        None, "--requests", help="Target request count (packs cycle/expand to fill; ≤8000)"
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Dry-run: show scenarios / expected policy tendencies without sending traffic."""
    from token_factory.demo import DemoRunner

    plan = DemoRunner(mock=True).plan(pack, seed=seed, requests=requests)
    if json_out:
        console.print_json(data=plan)
        return
    console.print(
        Panel.fit(
            f"[bold]Automated Demo Plan[/bold] · {plan.get('display_name')} ({plan['pack_id']})\n"
            f"{plan.get('description', '')}\n"
            f"Scenarios in pack: {plan.get('scenario_count')} · "
            f"Planned requests: {plan.get('planned_requests')}\n"
            f"[dim]Validates routing-policy execution — not a benchmark[/dim]"
        )
    )
    table = Table(title="Planned requests")
    table.add_column("#", justify="right")
    table.add_column("Scenario")
    table.add_column("Use case")
    table.add_column("Serving")
    table.add_column("Compute tendency")
    table.add_column("Inject")
    for i, sc in enumerate(plan.get("scenarios") or [], start=1):
        fam = sc.get("preferred_compute_family")
        if isinstance(fam, list):
            fam = ",".join(str(x) for x in fam)
        table.add_row(
            str(i),
            str(sc.get("display_name") or sc.get("id")),
            str(sc.get("use_case") or "—"),
            str(sc.get("serving_pattern") or "—"),
            str(fam or "—"),
            ",".join(sc.get("inject") or []) or "—",
        )
    console.print(table)
    cov = plan.get("coverage") or {}
    if cov:
        console.print(f"[dim]Coverage: {json.dumps(cov)}[/dim]")


@demo_app.command("run")
def demo_run_cmd(
    pack: str = typer.Option(
        "smoke",
        "--pack",
        "-p",
        help="smoke|executive|enterprise-mixed|observability|fallback",
    ),
    lifecycle: str = typer.Option("production", "--lifecycle", "-L"),
    traffic: str = typer.Option(
        "sequential", "--traffic", "-t", help="sequential|low|medium|high|mixed"
    ),
    requests: int | None = typer.Option(
        None, "--requests", help="Target request count (packs cycle/expand to fill; ≤8000)"
    ),
    concurrency: int | None = typer.Option(
        None, "--concurrency", "-c", help="Bounded concurrency (≤10)"
    ),
    seed: int | None = typer.Option(None, "--seed", help="Reproducible mixed packs"),
    inject: list[str] | None = typer.Option(
        None,
        "--inject",
        help=(
            "Failure injection (repeatable): preferred-endpoint-unavailable, "
            "no-radeon, no-epyc, no-local, lifecycle-restriction"
        ),
    ),
    ci: bool = typer.Option(False, "--ci", help="CI mode: exit 0 on policy validations; ignore latency"),
    mock: bool = typer.Option(
        False, "--mock", help="Force mock classify/chat adapters (no cluster required)"
    ),
    live: bool = typer.Option(False, "--live", help="Force live Gateway/SR adapters"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Run Automated Demo scenario pack (routing-policy + observability validation)."""
    from token_factory.demo import DemoRunner
    from token_factory.demo.metrics_server import metrics_endpoint_url, start_metrics_server

    # Prefer long-lived make-ui metrics server; start one if missing (CLI-only runs).
    metrics_listen = start_metrics_server()
    if metrics_listen and not ci:
        console.print(
            f"[dim]Demo metrics: {metrics_endpoint_url(port=metrics_listen[1])}[/dim]"
        )

    if mock and live:
        console.print("[red]Choose at most one of --mock / --live[/red]")
        raise typer.Exit(2)
    mock_flag: bool | None
    if mock:
        mock_flag = True
    elif live:
        mock_flag = False
    else:
        mock_flag = True if ci else None

    runner = DemoRunner(mock=mock_flag)
    run = runner.run(
        pack,
        lifecycle=lifecycle,
        traffic=traffic,
        requests=requests,
        concurrency=concurrency,
        seed=seed,
        inject=list(inject or []),
        ci=ci,
        mock=mock_flag,
    )
    summary = run.validation_summary or {}
    if json_out:
        console.print_json(data=run.to_dict())
    elif ci:
        console.print("Token Factory Policy Validation")
        console.print(f"{summary.get('requests', 0)} requests")
        dims = summary.get("dimensions") or {}
        for label, key in (
            ("classified", "classification"),
            ("policy-valid", "policy"),
            ("capability-valid", "capability"),
            ("lifecycle-valid", "lifecycle"),
        ):
            passed = (dims.get(key) or {}).get("PASS", 0)
            console.print(f"{passed} {label}")
        console.print(f"{summary.get('fallbacks', 0)} fallback")
        tel_pass = (dims.get("telemetry") or {}).get("PASS", 0)
        console.print(f"{tel_pass} telemetry emitted")
        console.print("PASS" if summary.get("policy_ok") else "FAIL")
    else:
        console.print(
            Panel.fit(
                f"[bold]Automated Demo[/bold] · {run.scenario_pack}\n"
                f"Run ID     {run.id}\n"
                f"Lifecycle  {run.lifecycle_mode} · traffic {run.traffic_profile}\n"
                f"Requests   {summary.get('requests')} · "
                f"passed {summary.get('passed')} · "
                f"warnings {summary.get('warnings')} · "
                f"failed {summary.get('failed')} · "
                f"fallbacks {summary.get('fallbacks')} · "
                f"runtime escalations {summary.get('runtime_escalations')}\n"
                f"Mock       {run.mock} · artifact {run.meta.get('artifact', '—')}\n"
                f"[dim]Routing-policy validation — not a benchmark[/dim]"
            )
        )
        table = Table(title="Request results")
        table.add_column("#", justify="right")
        table.add_column("Status")
        table.add_column("Scenario")
        table.add_column("Model / Compute")
        table.add_column("Fallback")
        table.add_column("Escalation")
        for r in run.requests:
            a = r.actual or {}
            model = a.get("selected_model") or "—"
            compute = a.get("selected_compute") or ""
            table.add_row(
                str(r.index + 1),
                r.overall().value,
                r.display_name or r.scenario_id,
                f"{model} / {compute}".strip(" /"),
                "yes" if a.get("fallback_used") else "",
                "yes" if a.get("runtime_escalation") else "",
            )
        console.print(table)

    if ci and not summary.get("policy_ok"):
        raise typer.Exit(1)


@demo_app.command("list")
def demo_list(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List available Automated Demo scenario packs."""
    from token_factory.demo import list_packs

    packs = list_packs()
    if json_out:
        console.print_json(data=packs)
        return
    table = Table(title="Automated Demo packs")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Scenarios", justify="right")
    table.add_column("Description")
    for p in packs:
        table.add_row(
            p["id"],
            p.get("display_name") or p["id"],
            str(p.get("scenario_count") or 0),
            (p.get("description") or "")[:80],
        )
    console.print(table)


@app.command()
def versions() -> None:
    """Show pinned component versions."""
    for key, value in PINNED_VERSIONS.items():
        console.print(f"{key}: {value}")


if __name__ == "__main__":
    app()
