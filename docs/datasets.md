# Datasets

A **dataset** in CogniDQ is the unit you author rules against. It is a
named, schema-aware view of a tabular source — a single Postgres table,
a CSV upload, a parquet file in object storage.

For the connection layer underneath, see [connectors.md](connectors.md).

---

## Lifecycle

```mermaid
flowchart LR
  register[Register dataset] --> infer[Infer schema]
  infer --> review[Review fields]
  review --> active[Active]
  active --> archive[Archived]
```

1. **Register** — point CogniDQ at a connection + table, or upload a
   CSV. Optionally provide a name and description.
2. **Infer schema** — the connector reads column names and types and
   stores a `dataset_fields` record per column.
3. **Review** — a workspace member reviews inferred fields and may add
   business labels (display name, sensitivity tag, glossary term).
4. **Active** — the dataset is selectable when authoring rules.
5. **Archived** — keeps history but cannot be selected for new rules.

## Anatomy

```jsonc
{
  "id": "ds_customers",
  "workspace_id": "ws_demo",
  "name": "customers",
  "description": "Synthetic customer records (demo)",
  "source": {
    "kind": "csv",                    // csv | postgresql | spark | ...
    "connection_id": null,            // for non-CSV
    "uri": "minio://dq-data-assets/uploads/ws_demo/customers.csv"
  },
  "schema": {
    "fields": [
      { "name": "id", "type": "uuid", "nullable": false, "is_primary_key": true },
      { "name": "email", "type": "string", "nullable": true },
      { "name": "country", "type": "string", "nullable": true },
      { "name": "signup_at", "type": "timestamp", "nullable": false }
    ],
    "row_count_estimate": 5000
  },
  "tags": ["demo", "synthetic"],
  "status": "active",
  "owner_user_id": "user_steward",
  "created_at": "2026-06-15T10:00:00Z"
}
```

## Source kinds

### CSV upload

Drop a CSV from the dataset registration page. The file is stored in
MinIO under `uploads/<workspace_id>/<filename>`. The CSV is parsed with
type inference (string / int / float / bool / date / timestamp); you
can override types per-column on the review screen.

Best for ad-hoc analysis and the demo flow.

### PostgreSQL table or view

Pick a connection, schema, and table. Schema is read from
`information_schema.columns`. Foreign-key information is read where
available and used to suggest cross-dataset consistency rules.

### Spark on object storage (experimental)

Point at a parquet/CSV path in MinIO/S3. The schema is inferred from
the file metadata. Rules will run via the Spark engine.

### Other databases (beta / experimental)

See [connectors.md](connectors.md) for the support matrix.

## Schema inference & overrides

Inferred types map to a normalised internal type system:

| Internal | Postgres | CSV (inferred) | Spark |
|---|---|---|---|
| `string` | text, varchar | string | StringType |
| `integer` | int, bigint | integer | LongType |
| `decimal` | numeric, decimal | float | DecimalType |
| `boolean` | bool | bool | BooleanType |
| `date` | date | date | DateType |
| `timestamp` | timestamptz, timestamp | iso8601 | TimestampType |
| `uuid` | uuid | uuid | StringType |
| `json` | jsonb | json | StringType (parsed) |
| `binary` | bytea | (n/a) | BinaryType |

You can override the inferred type per field. Rules respect the
overridden type.

## Field metadata

Each field has:

- `display_name` — human-friendly label
- `description` — what the field means
- `sensitivity` — `public` / `internal` / `confidential` / `restricted`
- `glossary_term` — optional reference to an enterprise glossary entry
- `is_primary_key` — used for stable evidence references
- `is_foreign_key_to` — `<dataset_id>.<column>`, used for suggestions

Sensitivity tags drive evidence masking. For example, fields tagged
`restricted` are masked in evidence by default.

## Browsing data

The dataset detail page shows:

- field list with metadata
- a small preview (first 50 rows by default; never the full table)
- per-field summary statistics (null %, distinct count, min/max for
  numerics, sample values for strings)

Preview queries are read-only and bounded by `LIMIT` clauses; they
respect `MAX_ROWS_RETURNED`.

## Sample / demo datasets

The seed loader (`scripts/seed_demo_data.py`) registers three datasets:

| Dataset | Rows | Quality issues seeded |
|---|---|---|
| `customers` | ~5 000 | ~3% null email; ~0.5% duplicate id; some invalid country codes |
| `orders` | ~30 000 | ~1% negative amount; some `shipped_at < ordered_at` |
| `payments` | ~25 000 | ~2% null `customer_id`; some duplicate transaction ids |

Source files are in `examples/datasets/` and `seed-data/`. All data is
synthetic; do not rely on it for anything real.

## Limits

- Datasets are scoped to a workspace and cannot be shared across
  workspaces directly. To share, register the same source in another
  workspace.
- CSV uploads are limited to 200 MB and 1 000 columns by default
  (configurable in backend settings).
- Schema inference for very wide tables (>1 000 columns) is slower; the
  UI will paginate the field list.
