# Contributing to CogniDQ

Thanks for your interest in contributing! This document explains how to
set up the project, what we expect from contributions, and how to get
your changes merged.

## Code of conduct

By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Quick links

- [Getting started](docs/getting-started.md) — set up the local stack
- [Architecture](docs/architecture.md) — how the system is wired
- [Open-source strategy](docs/open-source-strategy.md) — Core /
  Experimental / Enterprise classification
- [Security policy](SECURITY.md) — how to report vulnerabilities

## Ways to contribute

- **Report bugs** — open an issue with the *Bug report* template.
- **Improve docs** — typos, clarifications, missing pages.
- **Add tests** — both backend (pytest) and frontend (Vitest /
  Playwright) coverage are welcome.
- **Implement features** — open a *Feature request* issue first to
  discuss scope and design before writing code.
- **Triage issues** — confirm bug reports, ask for missing details,
  link duplicates.

## Development setup

Prerequisites:

- Docker + Docker Compose v2
- Python 3.11+
- Node.js 18+ (or use the frontend container)

```bash
git clone https://github.com/aiexplainedhub/cognidq.git
cd cognidq
cp backend/.env.example backend/.env
# Generate two Fernet keys and put them in backend/.env (see comments).
docker compose up -d
```

The frontend is at <http://localhost:5173>, backend API docs at
<http://localhost:8000/api/docs>.

For developer commands:

```bash
make help    # list common tasks
```

## Branch and commit conventions

- Base your branch on `open-source` (the working integration branch
  during the OSS launch period; this will be `main` after v0.1.0-alpha).
- Branch names: `feat/<short-slug>`, `fix/<short-slug>`,
  `docs/<short-slug>`, `chore/<short-slug>`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat: add accepted-values rule type`
  - `fix(api): return 404 instead of 500 when dataset is missing`
  - `docs: clarify rule-engine threshold semantics`

## Coding standards

### Backend (Python)

- Format with `ruff format` (or `black`) and lint with `ruff check`.
- Type hints are encouraged on public functions.
- Tests live under `backend/tests/{unit,integration,e2e}/`.
- New endpoints must include at least one integration test that exercises
  the auth/RBAC layer.

```bash
cd backend
ruff check .
ruff format .
pytest -q
```

### Frontend (TypeScript)

- ESLint + Prettier are run in CI.
- Components live under `frontend/src/components/`, pages under
  `frontend/src/pages/`.
- Use the existing API client (`frontend/src/services/`) — do not call
  `fetch` directly from components.

```bash
cd frontend
npm install
npm run lint
npm run test
npm run build
```

### Pre-commit (optional but recommended)

```bash
pip install pre-commit
pre-commit install
```

This runs the same checks CI runs, locally, on every commit.

## Tests

- All PRs must pass CI (lint + test + build).
- New features should include tests covering happy path + at least one
  failure / RBAC denial case.
- For UI work, add a Playwright spec under `frontend/tests/e2e/` if the
  flow is user-visible.

Run everything:

```bash
make test
```

## Documentation

- Code-level changes that alter behaviour or configuration must update
  the relevant page under `docs/`.
- Add a CHANGELOG entry under `Unreleased` in `CHANGELOG.md`.
- Do not include screenshots that show real customer or personal data.
  Use synthetic demo data.

## Pull request process

1. Open a draft PR early to get feedback.
2. Fill in the PR template.
3. Ensure CI is green.
4. Request review from a maintainer.
5. Address review comments by pushing additional commits (do not
   force-push during review unless asked).
6. Once approved, a maintainer will squash-merge.

We aim to give an initial response within a few business days, but
this is a best-effort, no-SLA project. See [SUPPORT.md](SUPPORT.md).

## What we will not accept

- Code that depends on private or paid services without a free local
  alternative.
- Code that breaks the local Docker Compose `up -d` flow.
- Code that adds telemetry / phone-home behaviour without a clear
  opt-in and a documented privacy policy.
- Real or scraped customer data.
- Hardcoded secrets, even as "examples".

## Areas where we'd love help

- More rule types and rule-type docs
- Connectors for additional databases (with tests)
- Frontend accessibility audit
- Internationalisation
- Better demo datasets and walkthroughs
- Performance benchmarks of the execution engine
- Replacing the experimental NL rule builder with something more reliable

Look for issues labeled `good first issue` and `help wanted`.

## Releasing

Maintainers cut releases by tagging from `main`:

```bash
git tag v0.1.0-alpha
git push --tags
```

CI builds and publishes release artifacts.

## License

By contributing, you agree that your contributions are licensed under
the [Apache License 2.0](LICENSE), per Section 5 of the license.
