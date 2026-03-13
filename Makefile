# =============================================================================
# SHATTERED - Development Commands
# =============================================================================
# Run `make help` to see all available targets.
# =============================================================================

.PHONY: help lint lint-fix format format-check test test-fast coverage quality pmat \
        pmat-score pmat-complexity pmat-debt pmat-dead pmat-hotspots \
        pre-commit pre-commit-all shell-lint shell-format install clean

SHELL_DIR := packages/arkham-shard-shell

# ---- Help ----

help: ## Show this help message
	@echo "SHATTERED Development Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ---- Python Quality ----

lint: ## Run ruff linter on all Python code
	ruff check packages/

lint-fix: ## Run ruff linter and auto-fix issues
	ruff check packages/ --fix

format: ## Format all Python code with ruff
	ruff format packages/

format-check: ## Check Python formatting without changes
	ruff format packages/ --check

# ---- Testing ----

test: ## Run all Python tests
	python3 -m pytest packages/ -v --tb=short

test-fast: ## Run tests without slow markers (quick feedback)
	python3 -m pytest packages/ -v --tb=short -x -q

test-frame: ## Run frame tests only
	python3 -m pytest packages/arkham-frame/tests/ -v

test-shard: ## Run tests for a specific shard (usage: make test-shard SHARD=ach)
	python3 -m pytest packages/arkham-shard-$(SHARD)/tests/ -v

coverage: ## Run tests with coverage report
	python3 -m pytest packages/ --cov=packages --cov-report=term-missing --tb=short

# ---- PMAT Quality ----

pmat: ## Run PMAT quality gate
	pmat quality-gate

pmat-score: ## Show repo health score (0-100)
	pmat repo-score

pmat-complexity: ## Run PMAT complexity analysis
	pmat analyze complexity --project-path .

pmat-debt: ## Run PMAT technical debt analysis
	pmat analyze satd --path .

pmat-dead: ## Run PMAT dead code detection
	pmat analyze dead-code --path .

pmat-hotspots: ## Show top complexity hotspots
	pmat analyze complexity --project-path . 2>&1 | grep -A 20 "Top Complexity Hotspots"

# ---- Pre-commit ----

pre-commit: ## Run pre-commit on staged files
	pre-commit run

pre-commit-all: ## Run pre-commit on all files
	pre-commit run --all-files

# ---- Frontend (Shell) ----

shell-lint: ## Run ESLint on shell UI
	cd $(SHELL_DIR) && npm run lint

shell-format: ## Check shell formatting with Prettier
	cd $(SHELL_DIR) && npm run format

shell-format-fix: ## Fix shell formatting with Prettier
	cd $(SHELL_DIR) && npm run format:fix

shell-build: ## Build the shell UI
	cd $(SHELL_DIR) && npm run build

# ---- Combined ----

check: lint format-check shell-lint shell-format ## Run all checks (no changes)
	@echo "All checks passed!"

fix: lint-fix format shell-format-fix ## Fix all auto-fixable issues
	@echo "All auto-fixes applied!"

all: check test pmat ## Run everything: lint + format + test + quality

# ---- Setup ----

install: ## Install all development dependencies
	@echo "Installing ruff..."
	@which ruff > /dev/null 2>&1 || uv tool install ruff
	@echo "Checking pmat..."
	@which pmat > /dev/null 2>&1 || (echo "Install pmat: cargo install pmat" && exit 0)
	@echo "Installing pre-commit hooks..."
	pre-commit install
	@echo "Installing shell dependencies..."
	cd $(SHELL_DIR) && npm install
	@echo "Done! Run 'make help' to see available commands."

clean: ## Clean build artifacts and caches
	find packages/ -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find packages/ -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find packages/ -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .ruff_cache .pytest_cache
	@echo "Cleaned!"
