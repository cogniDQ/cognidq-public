# Repository structure

This document describes the **current** layout of the CogniDQ repository
and the **target** layout for v1.0. They are not the same yet. Moving
the source into the target layout will happen in a focused PR and is
tracked on the [roadmap](../ROADMAP.md).

We document this now so newcomers and contributors are not confused by
the difference.

---

## Current layout (as of v0.1.0-alpha)

```
.
├── backend/                    # FastAPI service + Celery worker
│   ├── app/                    # application code (api, models, services)
│   ├── alembic/                # database migrations
│   ├── tests/                  # backend tests
│   ├── Dockerfile
│   ├── Dockerfile.spark-worker
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                   # React + Vite SPA
│   ├── src/
│   ├── public/
│   ├── tests/                  # Vitest + Playwright e2e
│   ├── Dockerfile
│   ├── package.json
│   └── .env.example
│
├── docs/                       # User documentation (this folder)
├── documentation/              # Legacy / internal-style docs (will be merged into docs/)
├── examples/                   # Sample datasets and rules
├── seed-data/                  # Synthetic CSV/JSON/parquet/xlsx datasets
├── scripts/                    # Operational scripts (init_db.sql, seed, etc.)
├── tests/                      # Cross-cutting / integration tests
├── monitoring/                 # Local Prometheus / Grafana config
├── ai_delivery/                # Agent-driven delivery scaffolding (internal)
├── qa/                         # QA fixtures and seeds
├── e2e_subtypes/               # Long-lived end-to-end harness scripts
├── todo-lists/                 # Internal planning artifacts
│
├── docker-compose.yml          # Local-dev stack
├── Makefile                    # Developer task runner
├── pyproject.toml              # Repo-wide Python tooling config (ruff, pytest)
├── .pre-commit-config.yaml     # Pre-commit hooks
├── README.md
├── LICENSE                     # Apache-2.0
├── NOTICE
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── SUPPORT.md
├── CHANGELOG.md
├── ROADMAP.md
└── .github/                    # Issue / PR templates, GitHub Actions
```

A handful of root-level Python scripts (`check_*.py`, `confirm_*.py`,
`qa_*.py`, `test_*.py`, `register_*.py`, `provision_tenant_ui.py`,
`fix_recon_flow.py`, etc.) are leftover ad-hoc operational tools from
earlier development. They are slated for cleanup before v1.0; do not
extend them. New equivalents should live under `scripts/`.

---

## Target layout (v1.0)

The plan is to move toward this layout once the move can be done
without breaking the existing Docker Compose stack and CI:

```
.
├── apps/
│   ├── frontend/               # was: ./frontend
│   ├── backend/                # was: ./backend
│   └── worker/                 # extracted from backend/app/workers (optional)
│
├── packages/
│   └── shared/                 # cross-app shared types / clients
│
├── infra/
│   ├── docker/                 # Dockerfiles + compose overlays
│   │   ├── docker-compose.yml
│   │   └── docker-compose.prod.yml
│   ├── postgres/               # init scripts
│   ├── redis/
│   ├── minio/
│   └── spark/
│
├── docs/                       # User documentation (consolidated)
├── examples/
│   ├── datasets/
│   ├── rules/
│   └── demo-scenarios/
├── scripts/
├── tests/                      # cross-package integration / e2e
├── .github/
├── README.md
├── LICENSE
├── NOTICE
├── ...
```

### Why this layout

- Clear separation between application code (`apps/`), infrastructure
  config (`infra/`), and reusable libraries (`packages/`).
- A single `infra/docker/docker-compose.yml` (and a `prod.yml` overlay)
  instead of one root file that mixes dev defaults and production
  concerns.
- Predictable for newcomers: matches the convention used by Turborepo,
  Nx, and most modern monorepos.

### Why we have not done it yet

- `docker-compose.yml` references `./backend` and `./frontend` directly.
  Moving the folders requires updating compose, Dockerfile build
  contexts, and a number of scripts in lockstep.
- `backend/Dockerfile.spark-worker` mounts the same source tree as the
  backend container; this needs to be re-thought as part of the move.
- CI configurations and any external badges referencing line numbers
  will break.

This is a tractable refactor but not an "almost no work" change. It is
on the roadmap for v0.2 / v1.0.

---

## Conventions

When adding new code, prefer the following so the eventual move is
mechanical:

- **Backend code** → `backend/app/<area>/` with a clear `area` namespace
  (e.g. `services/rules`, `services/datasources`).
- **Backend tests** → `backend/tests/{unit,integration,e2e}/`, mirroring
  the source tree under `unit/`.
- **Frontend code** → `frontend/src/<feature>/` with thin pages under
  `frontend/src/pages/`.
- **Frontend tests** → `frontend/tests/unit/` for Vitest,
  `frontend/tests/e2e/` for Playwright.
- **Documentation** → `docs/` (user-facing) only. Anything internal
  belongs in `documentation/internal/` (or a private repo).
- **Scripts** → `scripts/` for shell/Python operational scripts. Do not
  add new scripts at the repo root.
- **Sample data** → `examples/datasets/` (synthetic only).
- **Migrations** → `backend/alembic/versions/`. Always autogenerate, then
  hand-review.

---

## What goes where in this repo today

| If you want to … | Edit / add files in … |
|---|---|
| Add an API endpoint | `backend/app/api/v1/endpoints/` |
| Add a service / business logic | `backend/app/services/<area>/` |
| Add a database model | `backend/app/models/` and a new Alembic revision |
| Add a UI page | `frontend/src/pages/` and `frontend/src/router.ts` |
| Add a UI component | `frontend/src/components/` |
| Add a rule type | `backend/app/services/rule_engine/<rule_type>.py` (and tests) |
| Add a connector | `backend/app/services/datasources/connectors/` (and tests) |
| Add user-facing docs | `docs/<page>.md` |
| Add an example dataset | `examples/datasets/<name>.csv` (synthetic) |
| Add a script | `scripts/<name>.{sh,ps1,py}` |

When in doubt, open an issue and propose where it should live before
writing code.
