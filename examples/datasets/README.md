# Synthetic example datasets

Small CSV datasets used by the demo seed loader and as reference data
in the documentation.

> **All data is synthetic.** Names, emails, addresses, IDs, timestamps,
> and values were generated programmatically. Any resemblance to real
> people or organisations is coincidental.

---

## Files

| File | Rows | Intentional issues seeded |
|---|---|---|
| `customers.csv` | 30 | ~10% null email; 1 duplicate id; 1 invalid country |
| `orders.csv` | 40 | 2 negative amounts; 2 rows where `shipped_at < ordered_at` |
| `payments.csv` | 30 | 2 null `customer_id`; 1 duplicate `transaction_id`; 1 negative amount |
| `products.csv` | 12 | 1 null name; 1 negative price |

These are tiny on purpose — they live in the repo and are easy to
inspect by eye. The `make seed` flow can scale them up by replicating
rows with deterministic perturbation.

## How they're used

- `scripts/seed_demo_data.py` (the `make seed` target) reads them,
  registers them as datasets in the demo workspace, and creates the
  default rules in [`examples/rules/`](../rules/).
- `docs/first-check.md` walks through running rules against
  `customers.csv`.
- Some integration tests load the same CSVs as fixtures.

## Adding a new example dataset

If you contribute a new connector or rule type, please add a synthetic
CSV here that exercises the new code path. Keep the row count small
(≤100) and document the intentional issues in this README.

We do not accept real-world data — even "sanitised" — into the repo.
