"""Token Factory CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

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
    gateway = os.environ.get("TF_GATEWAY_URL", "http://localhost:8080")
    sr_api = os.environ.get("TF_SR_URL", "http://localhost:8081")
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


@app.command()
def ui() -> None:
    """Launch Streamlit UI locally."""
    ui_path = repo_root() / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)], check=False)


@app.command()
def versions() -> None:
    """Show pinned component versions."""
    for key, value in PINNED_VERSIONS.items():
        console.print(f"{key}: {value}")


if __name__ == "__main__":
    app()
