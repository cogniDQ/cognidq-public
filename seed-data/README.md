# Seed test datasets

Deterministic sample datasets used to exercise the connector layer end-to-end
during local development and CI smoke runs. They are intentionally small
(a few hundred rows each) so the suite stays fast.

## Datasets

| Name           | Rows | Notes                                                       |
| -------------- | ---: | ----------------------------------------------------------- |
| `customers`    |   50 | mix of nullable fields + ISO timestamps                     |
| `products`     |   30 | numeric + categorical fields, monetary `unit_price`         |
| `orders`       |  200 | references `customers.customer_id` and `products.product_id`|
| `employees`    |   25 | nullable `manager_id` (self-FK), nested `metadata` JSON     |
| `transactions` |  300 | `decimal` amounts + `currency` for FX tests                 |

Each dataset is written to **all four** local-file formats covered by the
connector P0 work:

```
seed-data/
  csv/<name>.csv
  xlsx/<name>.xlsx
  json/<name>.json
  parquet/<name>.parquet
```

## Regenerating

```powershell
# Windows
.\scripts\seed-test-data.ps1
```

```bash
# Linux / macOS / WSL
./scripts/seed-test-data.sh
```

The wrapper just calls [`scripts/seed_test_data.py`](../scripts/seed_test_data.py).
By default it generates files, loads them into a `seed` schema in Postgres,
and uploads them to MinIO under the bucket configured by
`SEED_MINIO_BUCKET` (default `dq-data-assets`). Pass `--no-postgres` /
`--no-minio` to skip steps when those services are unavailable.
