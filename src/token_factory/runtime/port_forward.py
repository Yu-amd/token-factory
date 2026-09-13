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


@dataclass
class PortForwardSpec:
    name: str
    namespace: str
    service: str
    local_port: int
    remote_port: int


DEFAULT_FORWARDS: list[PortForwardSpec] = [
    PortForwardSpec("ai-gateway", "envoy-gateway-system", "envoy-gateway", 8080, 80),
    PortForwardSpec("semantic-router-api", "vllm-semantic-router-system", "semantic-router", 8081, 8080),
    PortForwardSpec(
        "semantic-router-dashboard",
        "vllm-semantic-router-system",
        "semantic-router-dashboard",
        8700,
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


def _resolve_gateway_service() -> str | None:
    try:
        result = subprocess.run(
            [
                "kubectl", "get", "svc", "-n", "envoy-gateway-system",
                "-l", "gateway.envoyproxy.io/owning-gateway-name=semantic-router",
                "-o", "jsonpath={.items[0].metadata.name}",
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


def start_forwards(specs: list[PortForwardSpec] | None = None) -> list[dict[str, Any]]:
    specs = specs or DEFAULT_FORWARDS
    gateway_svc = _resolve_gateway_service()
    started: list[dict[str, Any]] = []

    for spec in specs:
        svc = gateway_svc if spec.name == "ai-gateway" and gateway_svc else spec.service
        if not _port_available(spec.local_port):
            stop_forward(spec.local_port)

        cmd = [
            "kubectl", "port-forward",
            "-n", spec.namespace,
            f"svc/{svc}",
            f"{spec.local_port}:{spec.remote_port}",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(0.3)
        entry = {
            "name": spec.name,
            "namespace": spec.namespace,
            "service": svc,
            "local_port": spec.local_port,
            "remote_port": spec.remote_port,
            "pid": proc.pid,
            "started_at": int(time.time()),
        }
        started.append(entry)

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
