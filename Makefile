.PHONY: help
help: ## Show the help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: install
install: ## install dependencies
	pip install -r requirements.txt

.PHONY: format
format: ## format code with black, isort
	black .
	isort .

.PHONY: lint
lint: ## check formatting with black, isort
	black --check .
	isort --check --diff .

.PHONY: type-check
type-check: ## run mypy
	mypy pytest_mypy_plugins

.PHONY: unit
unit: ## run pytest
	pytest

.PHONY: unit-cache
unit-cache: ## run mypy cache tests separately
	pytest pytest_mypy_plugins/tests/test_mypy_cache.py

.PHONY: test
test: lint type-check unit ## run all checks and tests
