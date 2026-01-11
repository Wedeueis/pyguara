# Makefile for Pyguara

.PHONY: help install install-dev test test-unit test-integration test-performance benchmark coverage lint format type-check clean clean-all docs-build docs-serve play version ci

# --- Default ---
help:  ## Show this help message
	@echo "PyGuara Development Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# --- Installation (The Fix) ---
# "uv sync --all-extras" installs Core + Dev + Docs + Benchmark dependencies in one go.
install:  ## Install ALL dependencies (core, dev, docs, benchmark)
	uv sync --all-extras

install-dev: install ## Alias for consistency

# --- Development ---
play:  ## Run the main game (User requested)
	uv run main.py

run: play ## Alias for 'play'

version:  ## Show current version (User requested)
	uv run python -c "from pyguara import __version__; print(__version__)"

# --- Testing ---
test:  ## Run standard tests (skips slow/perf)
	uv run pytest -m "not performance and not slow"

test-unit:  ## Run fast unit tests
	uv run pytest tests/ -m "not slow and not integration"

test-integration:  ## Run integration tests
	uv run pytest tests/integration/

test-performance:  ## Run performance analysis (User requested)
	uv run pytest -m performance --no-cov

benchmark:  ## Run benchmarks (User requested)
	uv run pytest -m performance --benchmark-only --benchmark-sort=mean

coverage:  ## Generate coverage report
	uv run pytest --cov=pyguara --cov-report=html --cov-report=term

coverage-check:  ## Fail if coverage is below 60%
	uv run pytest --cov=pyguara --cov-report=term --cov-fail-under=60

# --- Code Quality ---
lint:  ## Check code style
	uv run ruff check pyguara tests

format:  ## Format code
	uv run ruff format pyguara tests

format-check:  ## Checks format without changing
	uv run ruff format --check pyguara tests

type-check:  ## Run static type analysis
	uv run mypy pyguara

pre-commit-install: ## Install git hooks
	uv run pre-commit install

# --- Documentation ---
docs-build:  ## Build site (User requested)
	uv run mkdocs build

docs-serve:  ## Live preview of docs
	uv run mkdocs serve

# --- Cleanup (The Fix) ---
clean:  ## Clean standard build artifacts
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .coverage htmlcov .tox
	# FIX: Use exec rm -rf for folders
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Clean everything (including venv and logs)
	rm -rf .venv .ruff_cache site/ logs/ temp/
	@echo "Deep clean complete."

# --- CI Pipeline ---
ci: format lint type-check test-unit  ## Run local CI check
