# Example rules

This directory contains rule documents in the same JSON shape that the
API accepts. Each file is a single rule that targets one of the
synthetic datasets in [`../datasets/`](../datasets/).

You can:

- read them as a reference for the rule shape,
- POST them to `POST /api/v1/rules` to create them in your workspace
  (replace `dataset_id` with the id of your registered dataset),
- use them as starting points for your own rules.

The seed loader (`scripts/seed_demo_data.py`) creates equivalents of
these rules in the demo workspace on `make seed`.

## Files

| File | Type | Dataset | Should it pass on the seed data? |
|---|---|---|---|
| `customers-email-not-null.json` | completeness | customers | **fail** (~10% nulls) |
| `customers-id-unique.json` | uniqueness | customers | **fail** (1 dup) |
| `customers-country-accepted.json` | accepted_values | customers | **fail** (1 invalid) |
| `customers-email-valid.json` | validity | customers | passes (where present) |
| `orders-amount-non-negative.json` | range | orders | **fail** (2 negatives) |
| `orders-shipped-after-ordered.json` | consistency | orders | **fail** (2 violations) |
| `payments-customer-id-not-null.json` | completeness | payments | **fail** (2 nulls) |
| `payments-transaction-id-unique.json` | uniqueness | payments | **fail** (1 dup) |
| `payments-amount-positive.json` | comparison | payments | **fail** (1 negative) |
| `products-name-not-null.json` | completeness | products | **fail** (1 null) |
| `products-price-non-negative.json` | range | products | **fail** (1 negative) |

## Authoring conventions

- Names are lowercase with dots: `<dataset>.<column>.<predicate>`
  where reasonable.
- Severity matches the impact: `low` for hygiene, `medium` for default,
  `high` for customer-facing, `critical` for active harm.
- Thresholds default to `score >= 1.0` (zero failures) where the rule
  expresses a hard constraint, and `0.99` where some imperfection is
  expected.

## See also

- [docs/rule-types.md](../../docs/rule-types.md) — full rule type
  reference
- [docs/api-reference.md](../../docs/api-reference.md) — API shape for
  POSTing rules
