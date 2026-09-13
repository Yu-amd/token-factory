.PHONY: help preflight install apply verify test demo status dashboard grafana logs reset uninstall update-aim-catalog compile ports ui smoke-ui lint

REPO_ROOT := $(shell pwd)
VENV := $(REPO_ROOT)/.venv
PY := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,python3)

help:
	@echo "Token Factory Makefile targets:"
	@echo "  preflight            Validate toolchain + config"
	@echo "  compile              Generate manifests from config/"
	@echo "  install              Install full K8s stack (requires cluster)"
	@echo "  apply                Compile + apply generated manifests"
	@echo "  verify               Check deployments"
	@echo "  test                 Run unit tests"
	@echo "  demo                 Compile + run mock backend locally"
	@echo "  status               CLI health checks"
	@echo "  dashboard            Port-forward + verify SR dashboard"
	@echo "  ports                Start tracked port-forwards (:18080 gateway, :8081 SR API, …)"
	@echo "  ui                   Launch Streamlit UI (Playground: classify→AIM live stream)"
	@echo "  smoke-ui             Smoke-test Playground streaming path"
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
	$(PY) -m pytest tests/unit -q

demo: compile
	@echo "Starting mock backend on :8000 (Ctrl+C to stop)"
	$(PY) tests/mock_backends/server.py

status:
	$(PY) -m token_factory.cli.main status

dashboard:
	$(PY) -m token_factory.cli.main dashboard

grafana:
	$(PY) -m token_factory.cli.main grafana

ports:
	$(PY) -m token_factory.cli.main ports start

ui:
	cd ui && $(PY) -m streamlit run app.py

smoke-ui:
	bash scripts/smoke-playground-stream.sh

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
