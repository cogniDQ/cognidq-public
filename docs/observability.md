# Observability

CogniDQ ships with a basic observability surface that is enough to
operate the OSS stack. Production deployments will want more — see
[production-hardening.md](production-hardening.md).

---

## Health, readiness, version

The backend exposes three operator endpoints:

| Endpoint | Purpose | Auth |
|---|---|---|
| `GET /api/v1/system/health` | Liveness — is the process up? | none |
| `GET /api/v1/system/ready` | Readiness — can it serve traffic? | none |
| `GET /api/v1/system/version` | App version + git commit | any |

`/health` returns 200 as soon as the process is alive. Use it for
load-balancer liveness probes; do **not** use it for readiness.

`/ready` checks:

- DB connectivity (single `SELECT 1`),
- Redis connectivity,
- MinIO bucket reachability.

A failing dependency returns 503 with a JSON body:

```jsonc
{
  "status": "not_ready",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "minio": "error: connection refused"
  }
}
```

Use `/ready` for Kubernetes readiness probes and for compose-level
healthchecks.

## Metrics

`GET /api/v1/system/metrics` exposes Prometheus-format metrics. Key
series:

| Metric | Labels | Meaning |
|---|---|---|
| `http_requests_total` | method, route, status | request count |
| `http_request_duration_seconds` | method, route | request latency histogram |
| `db_pool_in_use` | — | connections currently checked out |
| `db_pool_size` | — | connection pool size |
| `celery_tasks_total` | task, status | task count by terminal state |
| `celery_task_duration_seconds` | task | task latency histogram |
| `rule_executions_total` | engine, status | rule execution count |
| `rule_execution_duration_seconds` | engine | rule execution latency |
| `evidence_objects_total` | — | evidence objects in MinIO |

Lock down `/metrics` at the reverse proxy in production — it leaks
information about routes and traffic shape.

## Logs

The backend, worker, and beat write structured JSON logs to stdout.
Each log line includes:

- `ts` (ISO 8601 UTC)
- `level`
- `logger`
- `message`
- `request_id` (for HTTP logs)
- `user_id`, `tenant_id`, `workspace_id` (when in a request context)
- `task_id`, `task_name` (for Celery logs)

Send container stdout to your log aggregator of choice (Loki, Datadog,
ELK).

## Tracing

Optional. The backend supports OpenTelemetry exporters when configured:

```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=cognidq-backend
```

When enabled, HTTP and DB spans are emitted; Celery tasks emit a span
per task. Tracing is off by default; the OSS image ships with the SDK
included but unconfigured to keep startup overhead low.

## Local Prometheus + Grafana

The repo includes a `monitoring/` directory with a minimal Prometheus
scrape config and Grafana dashboards. To run them locally:

```bash
docker compose -f docker-compose.yml -f monitoring/compose.yml up -d
```

(Uses the same compose network as the main stack.)

Default Grafana credentials are in `monitoring/README.md`. Change them
before exposing Grafana off your laptop.

## Flower (Celery monitoring)

Flower runs at <http://localhost:5555>. Defaults are protected by basic
auth (`FLOWER_BASIC_AUTH` in `backend/.env`). It shows queues, workers,
and task history; do not expose it to the public internet without
locking it down further.

## What you don't get out of the box

Things that the OSS stack intentionally **does not** include:

- Hosted SaaS metrics (Datadog, New Relic). Add via env-driven
  exporters; wiring is your responsibility.
- Anomaly detection / alerting on metrics. Use Grafana Alerting,
  Prometheus Alertmanager, or your existing alerting stack.
- A user-facing audit search UI. Audit events are exposed via the API
  (`GET /api/v1/audit`); a search UI is on the roadmap.
- Distributed tracing dashboards. The data is emitted; the dashboard is
  not bundled.

See [production-hardening.md](production-hardening.md) for the broader
operational checklist.
