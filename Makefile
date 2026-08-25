-include .env

UV ?= uv
RUN := $(UV) run
COMPOSE ?= docker compose
SCENARIO ?= SCN-001
EXPERIMENT ?=
EVIDENCE_ROOT ?= evidence

# Branch-coverage gate applies to the safety-critical core only (see ADR-005).
CORE_COV_TARGETS := \
	--cov=blackstart/core \
	--cov=blackstart/controller \
	--cov=blackstart/scenario_engine \
	--cov=blackstart/analysis \
	--cov=blackstart/evidence
CORE_COV_MIN := 90

.DEFAULT_GOAL := help
.PHONY: help bootstrap lint format typecheck test test-unit test-property \
        test-integration test-architecture coverage audit sbom up down health \
        demo experiment evidence compare docs clean check

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Create the virtualenv and install all dependency groups
	$(UV) sync --all-extras --dev
	@echo "bootstrap complete -> $$($(RUN) python -V)"

lint: ## Ruff lint + format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

format: ## Apply Ruff formatting and autofixes
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

typecheck: ## Strict mypy over package, services and tests
	$(RUN) mypy

test: ## Run the full test suite
	$(RUN) pytest

test-unit: ## Unit tests only
	$(RUN) pytest tests/unit -m unit

test-property: ## Hypothesis property-based tests only
	$(RUN) pytest tests/property -m property

test-integration: ## End-to-end scenario -> evidence -> metrics tests
	$(RUN) pytest tests/integration -m integration

test-architecture: ## Deployment topology / exposure tests
	$(RUN) pytest tests/architecture -m architecture

coverage: ## Enforce branch coverage on safety-critical core modules
	$(RUN) pytest $(CORE_COV_TARGETS) --cov-branch \
		--cov-report=term-missing --cov-report=xml \
		--cov-fail-under=$(CORE_COV_MIN)

audit: ## Audit resolved dependencies for known vulnerabilities
	$(UV) export --frozen --no-emit-project --all-extras --format requirements-txt \
		-o /tmp/blackstart-requirements.txt
	$(RUN) pip-audit --strict --requirement /tmp/blackstart-requirements.txt

sbom: ## Generate a CycloneDX SBOM
	$(UV) export --frozen --no-emit-project --all-extras --format requirements-txt \
		-o /tmp/blackstart-requirements.txt
	$(RUN) cyclonedx-py requirements /tmp/blackstart-requirements.txt \
		--output-format JSON --output-file sbom.json
	@echo "SBOM written to sbom.json"

up: ## Start the zoned container topology
	$(COMPOSE) up -d --build

down: ## Stop the topology and remove volumes
	$(COMPOSE) down -v --remove-orphans

health: ## Report health of every service in the topology
	$(RUN) python scripts/health.py

demo: ## Run the flagship backstop-on / backstop-off comparison
	$(RUN) blackstart experiment compare SCN-004 \
		--variant backstop-disabled --variant backstop-enabled \
		--evidence-root $(EVIDENCE_ROOT)/local

experiment: ## Run one scenario: make experiment SCENARIO=SCN-004
	$(RUN) blackstart experiment run $(SCENARIO) --evidence-root $(EVIDENCE_ROOT)/local

evidence: ## Verify evidence integrity: make evidence [EXPERIMENT=EXP-...]
	$(RUN) blackstart evidence verify $(EXPERIMENT) --evidence-root $(EVIDENCE_ROOT)

docs: ## Validate configuration/scenario schemas and documentation cross-links
	$(RUN) python scripts/check_docs.py

check: lint typecheck test coverage ## Full local quality gate

clean: ## Remove caches and locally generated artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml \
	       sbom.json build dist
	rm -rf $(EVIDENCE_ROOT)/local
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
