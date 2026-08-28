-include .env

UV ?= uv
RUN := $(UV) run
COMPOSE ?= docker compose
SCENARIO ?= SCN-001
EXPERIMENT ?=
EVIDENCE_ROOT ?= evidence/local
RESULT_ROOT ?= experiments/local/EXP-BS-001
RELEASE_ROOT ?= experiments/releases/v0.1.0

# Branch-coverage gate applies to the safety-critical core only (see ADR-005).
CORE_COV_TARGETS := \
	--cov=blackstart/core \
	--cov=blackstart/controller \
	--cov=blackstart/scenario_engine \
	--cov=blackstart/analysis \
	--cov=blackstart/evidence
CORE_COV_MIN := 90

.DEFAULT_GOAL := help
.PHONY: help bootstrap lint format typecheck test test-unit test-property test-properties \
        test-integration test-architecture coverage audit sbom up down health \
        demo run experiment evidence compare results release-artifacts docs clean \
        clean-results check quality-gate verify-attack-dataset

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

test-properties: test-property ## Alias used by the release reproduction directive

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

demo: experiment ## Alias for the complete flagship experiment

run: ## Run one scenario: make run SCENARIO=SCN-004
	$(RUN) blackstart experiment run $(SCENARIO) --evidence-root $(EVIDENCE_ROOT)

experiment: ## Run, verify, compare, plot, and report EXP-BS-001
	$(RUN) blackstart experiment flagship \
		--evidence-root $(EVIDENCE_ROOT) \
		--output-dir $(RESULT_ROOT)

evidence: ## Verify evidence integrity: make evidence [EXPERIMENT=EXP-...]
	$(RUN) blackstart evidence verify $(EXPERIMENT) --evidence-root $(EVIDENCE_ROOT)

results: clean-results experiment ## Regenerate the complete local result package

release-artifacts: ## Regenerate canonical v0.1 release evidence, report, and figures
	rm -rf $(RELEASE_ROOT)
	$(RUN) blackstart experiment flagship \
		--evidence-root $(RELEASE_ROOT)/evidence \
		--output-dir $(RELEASE_ROOT) \
		--assets-dir assets \
		--technical-report docs/BLACKSTART-v0.1-research-report.md \
		--readme README.md \
		--review-dir review

docs: ## Validate configuration/scenario schemas and documentation cross-links
	$(RUN) python scripts/check_docs.py

verify-attack-dataset: ## Retrieve and hash-check the pinned official ATT&CK ICS dataset
	$(RUN) python scripts/verify_attack_dataset.py

check: lint typecheck test coverage ## Full local quality gate

quality-gate: clean-results lint typecheck test test-properties coverage experiment evidence docs ## v0.1 gate
	@echo "BLACKSTART v0.1 QUALITY GATE: READY"

clean-results: ## Remove only locally generated experiment outputs
	rm -rf evidence/local experiments/local

clean: ## Remove caches and locally generated artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml \
	       sbom.json build dist
	rm -rf evidence/local experiments/local
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
