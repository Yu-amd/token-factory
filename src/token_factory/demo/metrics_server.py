"""Lightweight Prometheus text exposition for Automated Demo counters.

Serves demo counters on ``GET /metrics`` for in-cluster Prometheus scrape.

Two modes (same process can do both):

1. **In-process** — ``DemoInstrumentor.prometheus_text()`` when demos run in this
   process (UI / ``token-factory demo run``).
2. **File-backed** — reads ``generated/demo-metrics.prom`` (written by the
   instrumentor on each emit) so a long-lived ``python -m
   token_factory.demo.metrics_server`` can be scraped after short CLI runs exit.

Default listen port: ``TF_DEMO_METRICS_PORT`` (9108).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_METRICS_PORT = 9108

_server: ThreadingHTTPServer | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def metrics_port() -> int:
    raw = os.environ.get("TF_DEMO_METRICS_PORT", str(DEFAULT_METRICS_PORT))
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_METRICS_PORT


def metrics_file_path() -> Path:
    override = os.environ.get("TF_DEMO_METRICS_FILE")
    if override:
        return Path(override)
    from token_factory.runtime.paths import generated_dir

    return generated_dir() / "demo-metrics.prom"


def read_metrics_text() -> str:
    """Prefer live in-process counters; fall back to the on-disk snapshot."""
    try:
        from token_factory.demo.observability import get_instrumentor

        live = get_instrumentor().prometheus_text()
        if live.strip():
            return live
    except Exception:  # noqa: BLE001
        pass
    path = metrics_file_path()
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        pass
    return (
        "# Token Factory Automated Demo metrics\n"
        "# (empty — run a demo via UI or `token-factory demo run`)\n"
    )


class _MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] not in ("/metrics", "/"):
            self.send_error(404, "not found")
            return
        body = read_metrics_text().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        log.debug("demo-metrics: " + format, *args)


def start_metrics_server(
    port: int | None = None,
    *,
    bind: str = "0.0.0.0",
) -> tuple[str, int] | None:
    """Start a daemon HTTP server exposing ``/metrics`` (idempotent)."""
    global _server, _thread
    listen_port = DEFAULT_METRICS_PORT if port is None else port
    with _lock:
        if _server is not None:
            return bind, int(_server.server_address[1])
        try:
            server = ThreadingHTTPServer((bind, listen_port), _MetricsHandler)
        except OSError as exc:
            log.info(
                "demo metrics server not started on %s:%s (%s)",
                bind,
                listen_port,
                exc,
            )
            return None
        _server = server
        _thread = threading.Thread(
            target=server.serve_forever,
            name="tf-demo-metrics",
            daemon=True,
        )
        _thread.start()
        log.info(
            "demo metrics exposition listening on http://%s:%s/metrics",
            bind,
            listen_port,
        )
        return bind, listen_port


def stop_metrics_server() -> None:
    """Stop the metrics server if this process started it (tests)."""
    global _server, _thread
    with _lock:
        if _server is None:
            return
        _server.shutdown()
        _server.server_close()
        _server = None
        _thread = None


def metrics_endpoint_url(host: str = "127.0.0.1", port: int | None = None) -> str:
    return f"http://{host}:{port if port is not None else metrics_port()}/metrics"


def main(argv: list[str] | None = None) -> int:
    """CLI entry: ``python -m token_factory.demo.metrics_server``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Serve Automated Demo /metrics")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Listen port (default TF_DEMO_METRICS_PORT or {DEFAULT_METRICS_PORT})",
    )
    parser.add_argument(
        "--bind",
        default="0.0.0.0",
        help="Bind address (default 0.0.0.0 for kind bridge scrape)",
    )
    args = parser.parse_args(argv)
    port = args.port if args.port is not None else metrics_port()
    listen = start_metrics_server(port=port, bind=args.bind)
    if listen is None:
        print(
            f"port {port} busy — assuming another metrics server is already running",
            file=sys.stderr,
        )
        # Stay alive so Makefile `ui` background job does not exit as failure
        # when Streamlit later also tries to bind; scrape the existing listener.
        while True:
            time.sleep(3600)
        return 0  # pragma: no cover
    print(f"Serving Automated Demo metrics on {metrics_endpoint_url(port=listen[1])}")
    print(f"Snapshot file: {metrics_file_path()}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stop_metrics_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
