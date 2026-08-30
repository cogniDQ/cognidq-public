# CogniDQ developer task runner
#
# Usage:
#   make help        list available targets
#   make setup       prepare local environment (.env files, fernet keys)
#   make start       start the local stack (docker compose up -d)
#   make stop        stop the local stack
#   make logs        tail backend + worker logs
#   make migrate     apply database migrations
#   make seed        load demo seed data
#   make test        run backend + frontend tests
#   make lint        run linters
#   make format      auto-format code
#   make reset       wipe local volumes (DESTRUCTIVE)
#   make clean       remove generated artifacts
#
# Compose service names assumed:
#   backend, worker, beat, flower, frontend, db, redis, minio,
#   spark-master, spark-worker-1, spark-worker-2, spark-history.

SHELL := /bin/sh
PYTHON ?= python3
COMPOSE ?= docker compose
BACKEND_SERVICE ?= backend
WORKER_SERVICE ?= worker
FRONTEND_SERVICE ?= frontend

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ----------------------------------------------------------------------
# Setup
# ----------------------------------------------------------------------

.PHONY: setup
setup: ## Create local .env files and generate Fernet keys (idempotent)
	@# Root .env — read by Docker Compose for YAML variable interpolation.
	@if [ ! -f .env ]; then cp backend/.env.example .env && echo "created root .env (used by docker compose)"; else echo "root .env already exists"; fi
	@# Service-level copies
	@if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env && echo "created backend/.env"; else echo "backend/.env already exists"; fi
	@if [ ! -f frontend/.env ]; then cp frontend/.env.example frontend/.env && echo "created frontend/.env"; else echo "frontend/.env already exists"; fi
	@echo ""
	@echo "Edit .env and set the following required values:"
	@echo "  OPENAI_API_KEY         your OpenAI key (or leave placeholder to disable NL features)"
	@echo "  MINIO_ROOT_PASSWORD    any non-default password"
	@echo "  GF_SECURITY_ADMIN_PASSWORD  Grafana admin password"
	@echo "  SECRET_KEY             long random string (token signing)"
	@echo "  JWT_SECRET_KEY         long random string (JWT signing)"
	@echo ""
	@echo "Generated Fernet keys (paste BOTH into .env AND backend/.env):"
	@$(PYTHON) -c "from cryptography.fernet import Fernet; print('  DATASOURCE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())" || echo "  (pip install cryptography to auto-generate)"
	@$(PYTHON) -c "from cryptography.fernet import Fernet; print('  CREDENTIAL_ENCRYPTION_KEY=' + Fernet.generate_key().decode())" || true
	@echo ""
	@echo "Next: docker compose up -d  (or: make start)"

# ----------------------------------------------------------------------
# Stack lifecycle
# ----------------------------------------------------------------------

.PHONY: start
start: ## Start the full local stack
	$(COMPOSE) up -d

.PHONY: stop
stop: ## Stop the local stack
	$(COMPOSE) stop

.PHONY: down
down: ## Stop and remove containers (keeps volumes)
	$(COMPOSE) down

.PHONY: restart
restart: ## Restart backend, worker, beat, frontend
	$(COMPOSE) restart $(BACKEND_SERVICE) $(WORKER_SERVICE) beat $(FRONTEND_SERVICE)

.PHONY: logs
logs: ## Tail backend + worker logs
	$(COMPOSE) logs -f --tail=200 $(BACKEND_SERVICE) $(WORKER_SERVICE)

.PHONY: ps
ps: ## Show running services
	$(COMPOSE) ps

# ----------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply database migrations (runs SQL files in backend/scripts/migrations/)
	$(COMPOSE) exec $(BACKEND_SERVICE) python scripts/run_migrations.py

.PHONY: seed
seed: ## Load demo seed data (synthetic only)
	$(COMPOSE) exec $(BACKEND_SERVICE) python scripts/seed_demo_data.py

.PHONY: psql
psql: ## Open a psql shell on the app database
	$(COMPOSE) exec db psql -U postgres -d dataquality_db

# ----------------------------------------------------------------------
# Tests / quality
# ----------------------------------------------------------------------

.PHONY: test
test: test-backend test-frontend ## Run all tests

.PHONY: test-backend
test-backend: ## Run backend tests
	$(COMPOSE) exec -T $(BACKEND_SERVICE) pytest -q

.PHONY: test-frontend
test-frontend: ## Run frontend unit tests
	$(COMPOSE) exec -T $(FRONTEND_SERVICE) npm run -s test

.PHONY: test-e2e
test-e2e: ## Run Playwright e2e tests (requires running stack)
	cd frontend && npm run test:e2e

.PHONY: lint
lint: lint-backend lint-frontend ## Run all linters

.PHONY: lint-backend
lint-backend: ## Lint backend (ruff)
	$(COMPOSE) exec -T $(BACKEND_SERVICE) ruff check .

.PHONY: lint-frontend
lint-frontend: ## Lint frontend (eslint)
	$(COMPOSE) exec -T $(FRONTEND_SERVICE) npm run -s lint

.PHONY: format
format: ## Auto-format code (ruff + prettier)
	$(COMPOSE) exec -T $(BACKEND_SERVICE) ruff format .
	$(COMPOSE) exec -T $(FRONTEND_SERVICE) npm run -s format

.PHONY: typecheck
typecheck: ## Run TypeScript typecheck
	$(COMPOSE) exec -T $(FRONTEND_SERVICE) npm run -s typecheck

.PHONY: secret-scan
secret-scan: ## Run gitleaks against the working tree (requires gitleaks installed)
	gitleaks detect --no-git --redact --source . --report-format json --report-path .gitleaks-report.json || true
	@echo "Report: .gitleaks-report.json"

# ----------------------------------------------------------------------
# Connector integration test databases (separate from the default stack)
# ----------------------------------------------------------------------

TEST_COMPOSE ?= $(COMPOSE) -f docker-compose.yml -f docker-compose.test.yml

.PHONY: test-dbs
test-dbs: ## Start connector integration test databases (Postgres, MySQL, MSSQL, Oracle)
	$(TEST_COMPOSE) up dq-testdb dq-mysql dq-mssql dq-oracle -d
	@echo "Test databases started. See TEST_DATASOURCE_CREDENTIALS.md for connection details."

.PHONY: test-dbs-down
test-dbs-down: ## Stop and remove connector integration test database containers
	$(TEST_COMPOSE) rm -sf dq-testdb dq-mysql dq-mssql dq-oracle

# ----------------------------------------------------------------------
# Reset / clean
# ----------------------------------------------------------------------

.PHONY: clean
clean: ## Remove generated artifacts (logs, caches, build outputs)
	@echo "Removing logs and caches..."
	-rm -rf backend/logs/* backend/.pytest_cache backend/__pycache__
	-rm -rf frontend/dist frontend/.vite frontend/playwright-report frontend/test-results frontend/trace-debug*
	@echo "done"

.PHONY: reset
reset: ## DESTRUCTIVE: stop stack and remove volumes
	@echo "This will DELETE local data (postgres, minio, redis, spark)."
	@printf "Type 'yes' to continue: " && read ans && [ "$$ans" = "yes" ] || (echo "aborted"; exit 1)
	$(COMPOSE) down -v
	@echo "Volumes removed."
