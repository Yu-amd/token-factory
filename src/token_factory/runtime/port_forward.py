"""Port-forward manager with PID tracking — never pkill kubectl blindly."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from token_factory.runtime.paths import runtime_dir

STATE_FILE = "port-forwards.json"
SR_NAMESPACE = "vllm-semantic-router-system"
DASHBOARD_PORT_DEFAULT = 8700
DASHBOARD_PORT_ALTERNATES = (8701, 8702, 8703)


@dataclass
class PortForwardSpec:
    name: str
    namespace: str
    service: str
    local_port: int
    remote_port: int


DEFAULT_FORWARDS: list[PortForwardSpec] = [
    PortForwardSpec("ai-gateway", "envoy-gateway-system", "envoy-gateway", 8080, 80),
    PortForwardSpec("semantic-router-api", SR_NAMESPACE, "semantic-router", 8081, 8080),
    PortForwardSpec(
        "semantic-router-dashboard",
        SR_NAMESPACE,
        "semantic-router-dashboard",
        DASHBOARD_PORT_DEFAULT,
        8700,
    ),
    PortForwardSpec("grafana", "observability", "grafana", 3000, 3000),
    PortForwardSpec("prometheus", "observability", "prometheus", 9090, 9090),
]


def _state_path() -> Path:
    path = runtime_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / STATE_FILE


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"forwards": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kubectl_json(args: list[str]) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, FileNotFoundError, json.JSONDecodeError):
        return None


def resolve_gateway_service() -> str | None:
    try:
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "svc",
                "-n",
                "envoy-gateway-system",
                "-l",
                "gateway.envoyproxy.io/owning-gateway-name=semantic-router",
                "-o",
                "jsonpath={.items[0].metadata.name}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        name = result.stdout.strip()
        return name or None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def resolve_dashboard_service() -> tuple[str, int]:
    """Return (service_name, remote_port) for the SR dashboard."""
    data = _kubectl_json(["get", "svc", "-n", SR_NAMESPACE, "-o", "json"])
    if data:
        candidates = []
        for item in data.get("items", []):
            name = item.get("metadata", {}).get("name", "")
            if "dashboard" in name.lower():
                port = 8700
                for p in item.get("spec", {}).get("ports", []):
                    port = int(p.get("port", port))
                    break
                candidates.append((name, port))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0]
    return ("semantic-router-dashboard", 8700)


def dashboard_deployment_ready() -> tuple[bool, str]:
    data = _kubectl_json(["get", "deploy", "-n", SR_NAMESPACE, "-o", "json"])
    if not data:
        return False, "kubectl unavailable or namespace missing"
    for item in data.get("items", []):
        name = item.get("metadata", {}).get("name", "")
        if "dashboard" not in name.lower():
            continue
        status = item.get("status", {})
        ready = status.get("readyReplicas", 0) or 0
        desired = status.get("replicas", 0) or 0
        if ready >= 1 and ready == desired:
            return True, f"{name} ready ({ready}/{desired})"
        return False, f"{name} not ready ({ready}/{desired})"
    return False, "no dashboard Deployment found"


def find_available_local_port(preferred: int = DASHBOARD_PORT_DEFAULT) -> tuple[int, str | None]:
    """Return (port, note). If preferred is busy, try alternates."""
    ports_to_try = [preferred, *DASHBOARD_PORT_ALTERNATES]
    busy: list[int] = []
    for port in ports_to_try:
        if _port_available(port):
            note = None
            if port != preferred:
                note = f"port {preferred} occupied; using {port}"
            return port, note
        busy.append(port)
    raise RuntimeError(f"no free dashboard port in {ports_to_try} (all occupied)")


def _start_one_forward(
    spec: PortForwardSpec,
    *,
    service_override: str | None = None,
) -> dict[str, Any]:
    svc = service_override or spec.service
    if not _port_available(spec.local_port):
        stop_forward(spec.local_port)

    cmd = [
        "kubectl",
        "port-forward",
        "-n",
        spec.namespace,
        f"svc/{svc}",
        f"{spec.local_port}:{spec.remote_port}",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(0.5)
    return {
        "name": spec.name,
        "namespace": spec.namespace,
        "service": svc,
        "local_port": spec.local_port,
        "remote_port": spec.remote_port,
        "pid": proc.pid,
        "started_at": int(time.time()),
    }


def start_dashboard_forward(preferred_port: int = DASHBOARD_PORT_DEFAULT) -> dict[str, Any]:
    """Start a tracked port-forward to the SR dashboard."""
    svc, remote_port = resolve_dashboard_service()
    local_port, port_note = find_available_local_port(preferred_port)
    spec = PortForwardSpec(
        "semantic-router-dashboard",
        SR_NAMESPACE,
        svc,
        local_port,
        remote_port,
    )
    entry = _start_one_forward(spec)
    if port_note:
        entry["port_note"] = port_note

    state = _load_state()
    forwards = [f for f in state.get("forwards", []) if f.get("name") != spec.name]
    forwards.append(entry)
    _save_state({"forwards": forwards})
    return entry


def start_forwards(specs: list[PortForwardSpec] | None = None) -> list[dict[str, Any]]:
    specs = specs or DEFAULT_FORWARDS
    gateway_svc = resolve_gateway_service()
    dash_svc, dash_remote = resolve_dashboard_service()
    started: list[dict[str, Any]] = []

    for spec in specs:
        svc = spec.service
        if spec.name == "ai-gateway" and gateway_svc:
            svc = gateway_svc
        elif spec.name == "semantic-router-dashboard":
            svc = dash_svc
            spec = PortForwardSpec(
                spec.name, spec.namespace, svc, spec.local_port, dash_remote
            )
        started.append(_start_one_forward(spec, service_override=svc))

    _save_state({"forwards": started})
    return started


def stop_forward(local_port: int) -> bool:
    state = _load_state()
    stopped = False
    remaining = []
    for entry in state.get("forwards", []):
        if entry.get("local_port") == local_port:
            pid = entry.get("pid")
            if pid and _pid_alive(pid):
                try:
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            stopped = True
        else:
            remaining.append(entry)
    _save_state({"forwards": remaining})
    return stopped


def stop_all() -> int:
    state = _load_state()
    count = 0
    for entry in state.get("forwards", []):
        pid = entry.get("pid")
        if pid and _pid_alive(pid):
            try:
                os.killpg(pid, signal.SIGTERM)
                count += 1
            except ProcessLookupError:
                try:
                    os.kill(pid, signal.SIGTERM)
                    count += 1
                except ProcessLookupError:
                    pass
    _save_state({"forwards": []})
    return count


def list_forwards() -> list[dict[str, Any]]:
    state = _load_state()
    forwards = []
    alive_entries = []
    for entry in state.get("forwards", []):
        pid = entry.get("pid")
        alive = bool(pid and _pid_alive(pid))
        entry = {**entry, "alive": alive}
        forwards.append(entry)
        if alive:
            alive_entries.append({k: v for k, v in entry.items() if k != "alive"})
    if len(alive_entries) != len(state.get("forwards", [])):
        _save_state({"forwards": alive_entries})
    return forwards


def _port_available(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def spec_to_dict(spec: PortForwardSpec) -> dict[str, Any]:
    return asdict(spec)
