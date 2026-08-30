# Evidence

When a rule fails, CogniDQ stores a **sample of failing rows** as
*evidence* — proof of what the rule found, useful for triage and for
explaining failures to stakeholders.

Related: [rule-engine.md](rule-engine.md), [issues.md](issues.md).

---

## What is evidence?

For each `failed` execution, the engine collects:

- aggregate metrics (`rows_total`, `rows_failed`, `score`),
- a **sample** of failing rows (default: first 100),
- the rule snapshot at the time of execution (rule type, config,
  threshold).

The sample is written to object storage (MinIO / S3) at:

```
evidence/<workspace_id>/<execution_id>.json
```

The execution record stores `evidence_ref` pointing at this object.

## Format

```jsonc
{
  "execution_id": "exec_01HXYZ",
  "rule_snapshot": {
    "id": "rule_01HXYZ",
    "version": 3,
    "type": "completeness",
    "config": { "column": "email" },
    "threshold": { "operator": "gte", "score": 0.99 }
  },
  "metrics": {
    "rows_total": 5000,
    "rows_failed": 142,
    "score": 0.9716
  },
  "sample": [
    {
      "row_ref": { "id": "11111111-1111-1111-1111-111111111111" },
      "values": { "email": null, "country": "FR" }
    },
    {
      "row_ref": { "id": "22222222-2222-2222-2222-222222222222" },
      "values": { "email": null, "country": "DE" }
    }
    // ...
  ],
  "collected_at": "2026-06-15T10:00:01Z",
  "schema_version": 1
}
```

`row_ref` uses the dataset's primary key when available; otherwise it
includes a row-hash so steward UIs can deduplicate.

## Sample size

The sample size is controlled per workspace in **Settings → Evidence**
(default 100). Reasonable bounds:

- too small (<20): triage is hard.
- too large (>1000): storage and UI rendering get expensive.

The engine never collects all failing rows. By design, evidence is a
*sample*, not a complete record.

## Sensitivity and masking

Field-level sensitivity tags drive masking:

| Sensitivity | Default behaviour in evidence |
|---|---|
| `public` | included as-is |
| `internal` | included as-is |
| `confidential` | hashed or truncated |
| `restricted` | replaced with `***` |

Workspaces can override per-field. `governance_viewer` sees masked
evidence even for fields tagged `internal`.

> **Important:** masking happens in the application layer at evidence
> *collection* time. Masking is a defence-in-depth measure, not a
> primary security boundary. Do not register columns containing actual
> credentials, secrets, or PII you don't have a lawful basis to process
> just because masking exists.

## Retention

Evidence objects are kept according to the workspace setting
`EVIDENCE_RETENTION_DAYS` (default 90). A periodic Celery task deletes
older objects from MinIO and clears `evidence_ref` on the corresponding
execution rows.

`governance_viewer` can request *legal hold* on a specific evidence
object, which exempts it from the retention sweep until the hold is
released.

## Access

| Role | Read evidence |
|---|---|
| `platform_admin` | governed by tenant policy (see [rbac.md](rbac.md)) |
| `tenant_admin` | no |
| `workspace_administrator` / `data_engineer` / `data_steward` | yes |
| `business_analyst` | yes |
| `governance_viewer` | yes (masked) |

Read access is via the API:

```
GET /api/v1/executions/{execution_id}/evidence
```

The backend resolves `evidence_ref` to a presigned URL with a short
TTL; the frontend fetches the object client-side.

## Storage layout

Bucket layout (default bucket `dq-data-assets`):

```
dq-data-assets/
└── evidence/
    └── ws_demo/
        ├── exec_01HXYZ.json
        ├── exec_01HXYA.json
        └── ...
```

Production deployments should:

- give the backend / worker a least-privilege role limited to the
  `evidence/<workspace_id>/*` prefix when running per-workspace
  workers (advanced; see hardening doc),
- enable bucket-level versioning + lifecycle rules,
- enable server-side encryption (SSE-S3 or SSE-KMS).

See [production-hardening.md](production-hardening.md).

## Audit

Reading evidence is an audit event:

```jsonc
{
  "operation": "evidence.read",
  "actor": { "user_id": "...", "role_in_scope": "data_steward" },
  "resource": { "type": "execution", "id": "exec_01HXYZ" },
  "result": "success",
  "at": "2026-06-15T10:05:00Z"
}
```

Audit events are surfaced to `governance_viewer` and `tenant_admin`.

## Limitations

- Evidence is JSON; binary fields are base64-encoded and may be
  truncated (`MAX_FIELD_BYTES`, default 4 KB).
- For Spark executions on very large datasets, the failed-row sample is
  collected with `df.limit(N).collect()`; this is intentional but means
  the sample is not a uniform random sample.
- We do not yet expose a "give me the full failed-rows set" download.
  This is intentional — making it easy to download large failed-rows
  sets pulls source data into evidence storage in volumes the system
  isn't designed for.
