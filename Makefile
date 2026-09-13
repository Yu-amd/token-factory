.PHONY: help preflight install apply verify test demo status dashboard grafana logs reset uninstall update-aim-catalog compile ports ui smoke-ui recommend lint demo-smoke

REPO_ROOT := $(shell pwd)
VENV := $(REPO_ROOT)/.venv
PY := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)
USE_CASE ?= coding-assistant
OBJECTIVE ?= balanced

help:
	@echo "Token Factory Makefile targets:"
	@echo "  preflight            Validate toolchain + config"
	@echo "  compile              Generate manifests from config/"
	@echo "  install              Install full K8s stack (requires cluster)"
	@echo "  apply                Compile + apply generated manifests"
	@echo "  verify               Check deployments"
	@echo "  test                 Run unit tests"
	@echo "  demo                 Compile + run mock backend locally"
	@echo "  demo-smoke           Automated Demo smoke pack (mock adapters; policy validation)"
	@echo "  status               CLI health checks"
	@echo "  dashboard            Port-forward + verify SR dashboard"
	@echo "  ports                Start tracked port-forwards (:18080 gateway, :8081 SR API, …)"
	@echo "  ui                   Launch Streamlit UI (Playground, Automated Demo, Matrix, …)"
	@echo "  smoke-ui             Smoke-test Playground streaming path"
	@echo "  recommend            AMD Opinionated Routing (USE_CASE=… OBJECTIVE=…; see token-factory recommend -h)"
	@echo "  logs                 Tail semantic-router logs"
	@echo "  reset                Uninstall + delete generated/"
	@echo "  uninstall            Uninstall Helm releases"
	@echo "  update-aim-catalog   Regenerate catalog/aims.yaml"

preflight: compile
	$(PY) -m token_factory.cli.main preflight

compile:
	$(PY) -m token_factory.cli.main compile

install: compile
	bash scripts/install-all.sh

apply: compile
	bash scripts/apply-generated.sh

verify:
	$(PY) -m token_factory.cli.main verify

test:
	$(PY) -m pytest tests/unit tests/integration -q

demo: compile
	@echo "Starting mock backend on :8000 (Ctrl+C to stop)"
	$(PY) tests/mock_backends/server.py

demo-smoke:
	$(PY) -m token_factory.cli.main demo run --pack smoke --ci --mock

status:
	$(PY) -m token_factory.cli.main status

dashboard:
	$(PY) -m token_factory.cli.main dashboard

grafana:
	$(PY) -m token_factory.cli.main grafana

ports:
	$(PY) -m token_factory.cli.main ports start

ui:
	@mkdir -p generated
	@if curl -sf http://127.0.0.1:9108/metrics >/dev/null 2>&1; then \
		echo "Demo metrics already on :9108"; \
	else \
		echo "Starting demo metrics on :9108"; \
		$(PY) -m token_factory.demo.metrics_server --port 9108 >>generated/demo-metrics-server.log 2>&1 & \
		echo $$! > generated/demo-metrics-server.pid; \
		sleep 0.4; \
	fi
	@if curl -sf http://127.0.0.1:8501/_stcore/health >/dev/null 2>&1; then \
		echo "Token Factory UI already running at http://localhost:8501"; \
	elif ss -tlnH 2>/dev/null | grep -qE ':8501\b' || ss -tln 2>/dev/null | grep -q ':8501'; then \
		echo "Port 8501 is busy (not a healthy Streamlit). Free it, then re-run make ui."; \
		exit 1; \
	else \
		cd ui && PYTHONPATH=$(REPO_ROOT)/src $(PY) -m streamlit run app.py; \
	fi

smoke-ui:
	bash scripts/smoke-playground-stream.sh

recommend:
	$(PY) -m token_factory.cli.main recommend --use-case $(USE_CASE) --objective $(OBJECTIVE)

logs:
	kubectl logs -n vllm-semantic-router-system deploy/semantic-router -f --tail=100

reset: uninstall
	rm -rf generated/*
	$(PY) -m token_factory.cli.main ports stop || true

uninstall:
	bash scripts/uninstall-all.sh

update-aim-catalog:
	$(PY) scripts/generate-aim-catalog.py

lint:
	$(PY) -m ruff check src tests
