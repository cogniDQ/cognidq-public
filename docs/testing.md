# Testing

CogniDQ ships with three test layers. This page describes what they
cover and how to run them.

| Layer | Where | Tool | Speed |
|---|---|---|---|
| Backend unit | `backend/tests/unit/` | pytest | seconds |
| Backend integration | `backend/tests/integration/` | pytest + compose | tens of seconds |
| Frontend unit | `frontend/src/**/__tests__/` | Vitest | seconds |
| End-to-end (UI) | `frontend/tests/e2e/` | Playwright | minutes |

CI runs everything except long-running e2e on every push. Long-running
e2e runs nightly.

---

## Backend unit tests

Pure-Python tests that do not need any external service.

```bash
make test-backend
# or directly:
docker compose exec backend pytest backend/tests/unit -q
```

Conventions:

- One file per source module: `backend/tests/unit/services/test_rule_engine.py`.
- Fixtures live in `backend/tests/conftest.py` and per-package
  `conftest.py` files.
- Use `@pytest.mark.parametrize` for table-driven tests, especially for
  rule-type compilation.
- No network. No DB. No filesystem outside `tmp_path`.

## Backend integration tests

Tests that exercise the FastAPI app, the DB, Redis, and MinIO.

```bash
make test-backend
# In CI: services started via GitHub Actions services blocks.
# Locally:
docker compose up -d db redis minio
docker compose exec backend pytest backend/tests/integration -q
```

Conventions:

- Marked with `@pytest.mark.integration`.
- Use the test client (`TestClient`) for HTTP, not `requests` against a
  running server.
- Reset the DB between tests via the `db_session` fixture.
- Use `freezegun` for time-dependent assertions.

## Frontend unit tests

Vitest + React Testing Library.

```bash
make test-frontend
# or directly:
cd frontend && npm run test
```

Conventions:

- One spec per component: `Button.test.tsx` next to `Button.tsx`.
- Test behaviour, not implementation. Query by accessible role / label.
- Mock API calls at the service layer, not at `fetch`.

## End-to-end (Playwright)

The full stack in a browser.

```bash
make test-e2e
# or directly:
docker compose up -d
cd frontend && npm run test:e2e
```

Conventions:

- Specs live in `frontend/tests/e2e/`.
- Each spec resets state via the API (`/api/v1/system/test-reset`,
  available only when `ENABLE_TEST_RESET=true`).
- Auth uses programmatic login helpers, not the UI form, to keep specs
  fast.
- Each spec has a one-sentence comment at the top describing the user
  flow.

E2E specs are flaky-by-default in CI; a flake-retry policy of 1 retry
is acceptable. A persistently flaky spec should be either fixed or
quarantined with a TODO and a tracking issue.

## Smoke test

The simplest "everything works" check is the seeded demo flow:

```bash
make migrate seed
make test-e2e -- --grep "smoke"
```

This runs the canonical script: log in, run a rule, see evidence,
triage an issue.

## Coverage

Coverage is collected for the backend in CI and surfaced in the build
log. We do not enforce a coverage threshold yet; we will once the test
suite stabilises.

## Linting and formatting (counted as tests)

```bash
make lint           # ruff (backend) + eslint (frontend)
make format         # ruff-format + prettier
make typecheck      # tsc on the frontend
```

CI fails on lint, format, or type errors.

## Adding a test

A new feature is not "done" until it has at least one test. Minimum
bar:

- A unit test covering the happy path.
- A second unit test covering an obvious failure mode (bad input,
  missing field, denied permission).
- An integration test if it touches the DB or queue.
- An e2e test if it adds a new user-visible flow.

PRs without tests will be asked for them in review unless the change
is purely textual / documentation.

## Test data

- `examples/datasets/` — synthetic CSVs used by the demo and by some
  tests.
- `seed-data/` — synthetic CSV / JSON / parquet / xlsx for connector
  tests.

Test data must be synthetic. We do not accept real-world data, even
"sanitised", into the repo.
