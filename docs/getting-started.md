# Getting started

This guide takes you from zero to a running CogniDQ stack with demo
data, in about 5 minutes.

## Prerequisites

- **Docker** ≥ 24 and **Docker Compose v2** (`docker compose version`)
- **Python 3.11+** (only for generating Fernet keys; you can also do this
  inside the container)
- 8 GB free RAM, 10 GB free disk
- Ports `5173`, `8000`, `9000`, `9001`, `5436`, `5435`, `7077`, `8080`,
  `5555`, `18080`, `6379` available on the host

## 1. Clone

```bash
git clone https://github.com/cogniDQ/cognidq-public.git
cd cognidq-public
```

## 2. Configure environment

Copy the example env files:

```bash
# Root .env — read by Docker Compose for variable interpolation.
cp .env.example .env

# Service-level copies (runtime config injected into containers).
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

> **Why two files?**  Docker Compose resolves `${VARIABLE}` placeholders in
> `docker-compose.yml` from the **root `.env`** (not `backend/.env`).
> Both files must have matching values for the shared keys.

Edit **`.env`** (the root file) and set:

1. `OPENAI_API_KEY` — your OpenAI key (leave the placeholder to skip NL
   features; set `ENABLE_COMPLEX_FLOW_BUILDER=false` to suppress log noise).
2. Generate two **distinct** Fernet keys for `DATASOURCE_ENCRYPTION_KEY`
   and `CREDENTIAL_ENCRYPTION_KEY`:

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Run twice, paste the two different values.
3. Set `MINIO_ROOT_PASSWORD` to any non-default value.
4. Set `GF_SECURITY_ADMIN_PASSWORD` (Grafana admin password).
5. Generate secure random values for `SECRET_KEY` and `JWT_SECRET_KEY`:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Run twice and paste into the two fields.

Copy the same `*_ENCRYPTION_KEY`, `OPENAI_API_KEY`, `MINIO_*` values into
`backend/.env` as well so the container runtime environment matches.

## 3. Start the stack

```bash
docker compose up -d
```

First start pulls images and builds the backend; allow 3–5 minutes.

Check status:

```bash
docker compose ps
```

All services should be `healthy` or `running`.

## 4. Apply migrations

```bash
docker compose exec backend alembic upgrade head
```

This runs all 60+ ordered SQL migration files from
`backend/scripts/migrations/` and creates the full application schema.

## 5. Seed demo data

```bash
docker compose exec backend python scripts/seed_demo_data.py
```

This creates a demo tenant, a demo workspace, and demo users so you can
log in immediately. Sample datasets are in `examples/datasets/` and
`seed-data/`.

## 6. Open the app

| URL | What |
|---|---|
| <http://localhost:5173> | Frontend |
| <http://localhost:8000/api/docs> | API docs (Swagger UI) |
| <http://localhost:8000/api/redoc> | API docs (ReDoc) |
| <http://localhost:9001> | MinIO console |
| <http://localhost:8080> | Spark master UI |
| <http://localhost:5555> | Flower (Celery monitor; basic auth) |

## 7. Sign in

| Role | Email | Password |
|---|---|---|
| Platform admin | `admin@example.com` | `change-me-strong-password` |
| Tenant admin | `tenant.admin@example.com` | `change-me-strong-password` |
| Workspace admin | `ws.admin@example.com` | `change-me-strong-password` |
| Data steward | `steward@example.com` | `change-me-strong-password` |
| Viewer | `viewer@example.com` | `change-me-strong-password` |

> **Demo passwords are intentionally identical and weak.** They exist
> only to make the demo painless. **Never** use them outside your local
> laptop. See [production-hardening.md](production-hardening.md).

## 8. Run your first check

Continue with [first-check.md](first-check.md).

---

## Useful commands

```bash
make help          # list all developer tasks
make logs          # tail backend + worker
make psql          # open psql on the app DB
make seed          # re-seed demo data
make reset         # DESTRUCTIVE: wipe local volumes
```

## Troubleshooting

### `docker compose up` exits immediately with "variable is not set"

Docker Compose reads `${VARIABLE:?...}` placeholders from the **root `.env`**
file (same directory as `docker-compose.yml`), **not** from `backend/.env`.

```bash
# Make sure root .env exists:
ls .env          # should exist
ls backend/.env  # should also exist

# If root .env is missing:
cp .env.example .env
# Then fill in OPENAI_API_KEY, *_ENCRYPTION_KEY, MINIO_ROOT_PASSWORD,
# GF_SECURITY_ADMIN_PASSWORD, SECRET_KEY, JWT_SECRET_KEY.
```

### `docker compose up` exits immediately (other reasons)

Inspect logs:
```bash
docker compose logs backend | head -100
```

Other common causes:
- Encryption key left as the placeholder `replace-with-fernet-key-generated-locally`.
- Port 5436 / 5173 / 8000 already in use on the host.

### Login fails with 401

- Make sure you ran `make migrate` and then `make seed`.
- Confirm the demo user exists:
  ```bash
  make psql
  select email, status, platform_role from users;
  ```

### `python: can't open file 'scripts/seed_demo_data.py'`

You are likely running `make seed` before migrations. Apply migrations first:
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_demo_data.py
```

### "OpenAI API key invalid"

The default `OPENAI_API_KEY` is a placeholder. Either set a real key or
disable the experimental NL flow with
`ENABLE_COMPLEX_FLOW_BUILDER=false` in `backend/.env`. The core rule
flow works without OpenAI.

### Frontend cannot reach backend

The frontend container uses Vite's dev proxy. `VITE_API_URL` must be **empty**
in `frontend/.env`. If you accidentally set it to `http://localhost:8000/api/v1`,
the requests go to localhost inside the container (which has no backend).

```bash
# Fix:
grep VITE_API_URL frontend/.env    # should show: VITE_API_URL=
```

### Permission denied on a script

```bash
chmod +x scripts/*.sh
```

### Reset everything

```bash
make reset
docker compose up -d
make migrate seed
```

---

## What next

- [first-check.md](first-check.md) — run your first data quality rule
- [architecture.md](architecture.md) — how the system is wired
- [rule-engine.md](rule-engine.md) — supported rule types
- [rbac.md](rbac.md) — roles and permissions
