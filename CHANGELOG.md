# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/)
once we reach `1.0.0`. Pre-1.0 releases may include breaking changes in
minor versions; breaking changes are explicitly called out below.

---

## [Unreleased]

### Added
- Synthetic example datasets in `examples/datasets/` (customers, orders,
  payments, products) with intentional quality issues seeded.
- Example rules in `examples/rules/` corresponding to the datasets,
  in the JSON shape accepted by `POST /api/v1/rules`.
- `docs/database.md` covering migrations, seed loader, backups, and
  performance notes.
- `docs/publishing-to-fresh-repo.md` and
  `scripts/create_public_snapshot.{ps1,sh}` to publish CogniDQ as a
  brand-new public repository with a single clean commit (the
  recommended path over Git history rewrites).

---

## [0.1.0-alpha] — 2026-06-15

The first public release of CogniDQ. See
[release-notes/v0.1.0-alpha.md](release-notes/v0.1.0-alpha.md) for the
narrative announcement.

### Added
- Apache-2.0 `LICENSE`, `NOTICE`, and `docs/licensing.md`.
- Open-source strategy docs: `docs/product-scope.md`,
  `docs/open-source-strategy.md`, `docs/enterprise-edition.md`.
- Production-hardening checklist: `docs/production-hardening.md`.
- User documentation under `docs/`: `getting-started.md`,
  `first-check.md`, `architecture.md`, `rule-engine.md`,
  `rule-types.md`, `connectors.md`, `datasets.md`, `rbac.md`,
  `tenant-workspace-model.md`, `issues.md`, `incidents.md`,
  `evidence.md`, `api-reference.md`, `configuration.md`,
  `observability.md`, `deployment.md`, `demo-walkthrough.md`,
  `testing.md`, `repository-structure.md`, `known-limitations.md`.
- Asset directory placeholder: `docs/assets/README.md`.
- Security artifacts: `security/secret-scan-report.md`,
  `security/internal-reference-audit.md`,
  `security/git-history-cleanup.md`.
- Community files: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`,
  `SECURITY.md`, `SUPPORT.md`.
- GitHub issue and pull-request templates under `.github/`.
- GitHub Actions workflows: `.github/workflows/ci.yml` (backend +
  frontend + compose-config), `.github/workflows/security.yml`
  (gitleaks, pip-audit, npm-audit).
- Pre-commit configuration: `.pre-commit-config.yaml`.
- Repo-wide tooling config: root `pyproject.toml` (ruff + pytest).
- Developer task runner: `Makefile` with help/setup/start/stop/logs/
  migrate/seed/test/lint/format/secret-scan/reset targets.
- Release-notes scaffolding: `release-notes/v0.1.0-alpha.md`.
- `ROADMAP.md` and this `CHANGELOG.md`.

### Changed
- Replaced previous MIT license with Apache-2.0 for the open-source
  release.
- Sanitized 52 files containing the former maintainer's personal email
  and a shared QA password; replaced with neutral placeholders
  (`admin@example.com`, `change-me-strong-password`).
- Sanitized 28 additional files containing per-role QA test passwords
  (`Qa<Role>!2026` pattern) used by SQL seed migrations, Python
  seeders, and Playwright e2e specs. All replaced with the unified
  demo placeholder `change-me-strong-password` so seed/login round-trip
  still works.
- Replaced a real-looking Fernet key in `backend/.env.example` with a
  placeholder and instructions to generate one locally.
- Expanded `.gitignore` to cover `.env.*`, secrets material, common
  local artifacts, and IDE/agent config folders.

### Removed
- `body.json`, `short-memory.docx`, `discovery_extract.txt` —
  ad-hoc development / discovery artifacts.
- `frontend/trace-debug/`, `frontend/trace-debug2/`,
  `frontend/test-results/` — accidentally committed Playwright run
  artifacts.
- `.claude/` — local agent IDE settings.
- `backend/celerybeat-schedule` — runtime Celery state file.

### Security
- Documented a HIGH-severity finding: a real Fernet key
  (`vspbBrS-…` — value redacted) was previously present
  in `backend/.env.example`. **The key must be considered compromised
  and rotated wherever it was deployed.** See
  `security/secret-scan-report.md` §1.1.
- Documented Git-history considerations and remediation strategies in
  `security/git-history-cleanup.md`. Pre-existing history still
  contains the leaked values; users publishing this repo publicly must
  either rewrite history or publish a fresh snapshot before going
  public.

---

## [Older]

This release is the first public one. There is no prior public history.

[Unreleased]: https://github.com/aiexplainedhub/cognidq/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/aiexplainedhub/cognidq/releases/tag/v0.1.0-alpha
