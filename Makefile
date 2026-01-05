# Makefile for Pyguara development

.PHONY: help install install-dev test test-cov test-unit test-slow test-integration test-performance test-cli lint format format-check type-check pre-commit-install pre-commit-run docs-build docs-serve docs-deploy play benchmark build clean dev-setup dev-check ci quick-test debug-test version info

# Default target
help:  ## Show this help message
	@echo "PyGuara Development Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# Installation
install:  ## Install the package
	uv pip install -e .

install-dev:  ## Install with development dependencies
	uv pip install -e ".[dev,docs,benchmark]"

# Core Testing
test:  ## Run all tests without coverage
	uv run pytest -m "not performance"

test-cov:  ## Run tests with coverage report (85%+ target)
	uv run pytest --cov=pyguara --cov-report=html --cov-report=term --cov-fail-under=85

test-unit:  ## Run core and combat unit tests
	uv run pytest tests/ -m "not slow"

test-slow:  ## Run slow/performance tests
	uv run pytest -m slow

quick-test:  ## Run tests stopping at first failure (fast)
	uv run pytest -x --no-cov

debug-test:  ## Run tests with verbose debugging output
	uv run pytest -v -s --no-cov

benchmark:  ## Run performance benchmarks
	uv run pytest -m performance --benchmark-only --benchmark-sort=mean

test-integration:  ## Run full system integration tests
	uv run pytest tests/integration/ --no-cov

test-performance:  ## Run performance analysis tests
	uv run pytest -m performance --no-cov

test-cli:  ## Run CLI system tests
	uv run pytest tests/cli/ --no-cov

# Code Quality
lint:  ## Run all linting tools
	uv run ruff --check pyguara tests

format:  ## Format code with black and isort
	uv run ruff format pyguara tests

format-check:  ## Check code formatting without making changes
	uv run ruff format --check pyguara tests

type-check:  ## Run type checking with mypy
	uv run mypy pyguara

# Pre-commit hooks
pre-commit-install:  ## Install pre-commit hooks
	uv run pre-commit install

pre-commit-run:  ## Run pre-commit hooks on all files
	uv run pre-commit run --all-files

# Documentation
docs-build:  ## Build documentation
	uv run mkdocs build

docs-serve:  ## Serve documentation locally
	uv run mkdocs serve

docs-deploy:  ## Deploy documentation (for CI/CD)
	uv run mkdocs gh-deploy

# Demos - Gameplay
play: ## Run the main game
	uv run main.py

# Build and Distribution
build:  ## Build the package
	uv build

clean:  ## Clean build artifacts and caches
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .tox/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

clean-all: clean ## Clean everything including caches, logs, saves, and virtual environments
	@echo "Removing additional caches, logs, saves, and temp files..."
	rm -rf .ruff_cache/ site/ temp/ logs/ saves/ custom_saves/ demo_saves/ screenshots/
	@echo "Removing virtual environments..."
	rm -rf .venv/ .env/ env/ venv/ ENV/ env.bak/ venv.bak/
	@echo "Full cleanup complete."

# Development Workflows
dev-setup: install-dev pre-commit-install  ## Set up development environment

dev-check: format-check lint type-check test-cov ## Run all quality checks

ci: format-check lint type-check test-cov benchmark  ## Run CI pipeline with comprehensive tests

# Utilities
version:  ## Show current version
	uv run python -c "from pyguara import __version__; print(__version__)"

info:  ## Show environment and package information
	@echo "Python version: $(shell python --version)"
	@echo "UV version: $(shell uv --version)"
	@echo "Package version: $(shell uv run python -c \"from reclaimer import __version__; print(__version__)\")"
	@echo "Dependencies:"
	@uv pip list
