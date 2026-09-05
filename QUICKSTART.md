# Quick Start

> For the full guide with prerequisites and troubleshooting, see
> [docs/getting-started.md](docs/getting-started.md).

## 5-minute setup

```bash
# 1. Clone
git clone https://github.com/cogniDQ/cognidq-public.git
cd cognidq-public

# 2. Create env files
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 3. Edit .env — fill in these required values:
#    OPENAI_API_KEY            your OpenAI key (leave placeholder to skip NL features)
#    DATASOURCE_ENCRYPTION_KEY generated Fernet key (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#    CREDENTIAL_ENCRYPTION_KEY second generated Fernet key (different from the first)
#    MINIO_ROOT_PASSWORD        any non-default password
#    GF_SECURITY_ADMIN_PASSWORD Grafana admin password
#    SECRET_KEY                 random hex string (python -c "import secrets; print(secrets.token_hex(32))")
#    JWT_SECRET_KEY             second random hex string
#    Copy DATASOURCE_ENCRYPTION_KEY + CREDENTIAL_ENCRYPTION_KEY into backend/.env too.

# 4. Start the stack (first run builds the backend image; allow ~5 min)
docker compose up -d

# 5. Apply database migrations
docker compose exec backend alembic upgrade head

# 6. Seed demo users + demo content
docker compose exec backend python scripts/seed_demo_data.py
```

Open **http://localhost:5173** and sign in:

| Email | Password | Role |
|---|---|---|
| `admin@example.com` | `change-me-strong-password` | Platform admin |
| `steward@example.com` | `change-me-strong-password` | Data steward (workspace) |

The Demo Workspace comes pre-loaded with a live connection, datasets,
glossary terms, DQ rules, a flow, open issues, and one real flow run —
so every page has something to explore.

## Useful URLs

| URL | What |
|---|---|
| http://localhost:5173 | Frontend |
| http://localhost:8000/api/docs | API docs (Swagger UI) |
| http://localhost:9001 | MinIO console |
| http://localhost:8080 | Spark master UI |
| http://localhost:5555 | Flower (Celery monitor) |

## Common commands

```bash
make help           # list all developer tasks
make logs           # tail backend + worker logs
make migrate        # re-apply migrations
make seed           # re-seed demo data
make test-dbs       # start connector integration test databases
make reset          # DESTRUCTIVE: wipe all local volumes
```

## Troubleshooting

**`docker compose up` exits immediately with "variable is not set"**  
The root `.env` file is missing or incomplete. Docker Compose reads required
variables (`OPENAI_API_KEY`, `*_ENCRYPTION_KEY`, `MINIO_ROOT_PASSWORD`,
`GF_SECURITY_ADMIN_PASSWORD`) from `.env` in the project root — not from
`backend/.env`.

**Migrations**  
Migrations run through Alembic, which wraps the ordered SQL files in
`backend/scripts/migrations/`:
```bash
docker compose exec backend alembic upgrade head
```

**Login returns 401**  
Run `make seed` to create the demo users after migrations have been applied.

**API calls fail from the browser**  
`VITE_API_URL` in `frontend/.env` must be **empty** so requests go through
the Vite dev proxy. If it is set to `http://localhost:8000/api/v1`, clear it.
