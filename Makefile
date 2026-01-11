# Makefile for Pyguara

.PHONY: help install test test-unit test-integration test-performance benchmark coverage coverage-check lint format format-check type-check clean clean-all docs-build docs-serve run version ci pre-commit-install build

# --- Default ---
help:  ## Show this help message
	@echo "PyGuara Development Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# --- Installation ---
install:  ## Install ALL dependencies (core, dev, docs, benchmark)
	uv sync --all-extras

pre-commit-install: ## Install git hooks
	uv run pre-commit install

# --- Development ---
run:  ## Run the main game
	uv run main.py

version:  ## Show current version
	uv run python -c "from pyguara import __version__; print(__version__)"

# --- Build & Distribution ---
build:  ## Build the package (sdist and wheel)
	uv build

# --- Testing ---
test:  ## Run standard tests (skips slow/perf)
	uv run pytest -m "not performance and not slow"

test-unit:  ## Run fast unit tests
	uv run pytest tests/ -m "not slow and not integration"

test-integration:  ## Run integration tests
	uv run pytest tests/integration/

test-performance:  ## Run performance analysis
	uv run pytest -m performance --no-cov

benchmark:  ## Run benchmarks
	uv run pytest -m performance --benchmark-only --benchmark-sort=mean

coverage:  ## Generate coverage report
	uv run pytest --cov=pyguara --cov-report=html --cov-report=term

coverage-check:  ## Fail if coverage is below 60%
	uv run pytest --cov=pyguara --cov-report=term --cov-report=xml --cov-fail-under=60

# --- Code Quality ---
lint:  ## Check code style
	uv run ruff check pyguara tests

format:  ## Format code
	uv run ruff format pyguara tests

format-check:  ## Verify formatting (for CI)
	uv run ruff format --check pyguara tests

type-check:  ## Run static type analysis
	uv run mypy pyguara

# --- Documentation ---
docs-build:  ## Build documentation site
	uv run mkdocs build

docs-serve:  ## Live preview of docs
	uv run mkdocs serve

docs-deploy:  ## Deploy documentation to GitHub Pages
	uv run mkdocs gh-deploy --force

# --- Cleanup ---
clean:  ## Clean standard build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .coverage htmlcov .tox
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Clean everything (including venv and logs)
	rm -rf .venv .ruff_cache site/ logs/ temp/
	@echo "Deep clean complete."

# --- CI Pipeline ---
ci: format-check lint type-check test-unit coverage-check build ## Run full local CI pipeline
