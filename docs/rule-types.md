# Rule types

This is the catalog of rule types supported by CogniDQ in
`v0.1.0-alpha`. For the engine fundamentals (scoring, execution,
evidence), see [rule-engine.md](rule-engine.md).

> Status legend:
> - **stable** — works on PostgreSQL with tests; expected to keep working.
> - **beta** — code path exists, lightly tested.
> - **experimental** — works on a narrow happy path, may be removed or
>   replaced before v1.0.

Examples for each type live in `examples/rules/`.

---

## completeness — *stable*

Fail rows where the configured column is `NULL` (or empty string for
text columns, configurable).

```yaml
type: completeness
config:
  column: email
  treat_empty_string_as_null: true     # default true
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `column` | string | required | column name on the dataset |
| `treat_empty_string_as_null` | bool | true | also fail on `''` |
| `treat_whitespace_as_null` | bool | false | also fail on `'   '` |

**Score** = `non-null rows / total rows`.

---

## uniqueness — *stable*

Fail rows whose configured column (or composite key) value is
duplicated in the dataset.

```yaml
type: uniqueness
config:
  columns: [customer_id]
  ignore_nulls: true                   # default true
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `columns` | list[string] | required | one or more columns; composite key supported |
| `ignore_nulls` | bool | true | rows with any null in the key are skipped |

**Score** = `unique rows / total considered rows`.

---

## validity — *stable*

Fail rows whose value does not match a built-in validator.

```yaml
type: validity
config:
  column: email
  validator: email                     # email | url | uuid | ipv4 | ipv6
```

Supported validators in v0.1: `email`, `url`, `uuid`, `ipv4`, `ipv6`,
`isodate`, `iso8601`, `phone_e164`.

For more flexible patterns, use the `regex` rule type.

---

## consistency — *beta*

Fail rows where two columns disagree according to a comparator.

```yaml
type: consistency
config:
  left: shipped_at
  right: ordered_at
  operator: ">="                       # >, >=, <, <=, ==, !=
  null_policy: ignore                  # ignore | fail | pass
```

Cross-dataset consistency (compare a column in dataset A to one in
dataset B that share a connection) is supported via:

```yaml
type: consistency
config:
  left:
    dataset: orders
    column: customer_id
  right:
    dataset: customers
    column: id
  operator: in                          # value of left must exist in right
```

---

## comparison — *beta*

Fail rows where a column compared to a literal does not satisfy the
operator. Useful for absolute bounds.

```yaml
type: comparison
config:
  column: amount
  operator: ">="
  value: 0
```

For ranges (`min ≤ value ≤ max`), use `range` instead.

---

## accepted_values — *stable*

Fail rows whose column value is not in a fixed set.

```yaml
type: accepted_values
config:
  column: country
  values: [US, UK, FR, DE, IT, ES]
  case_sensitive: false                # default false
```

---

## regex — *stable*

Fail rows whose column does not match a regex.

```yaml
type: regex
config:
  column: phone
  pattern: '^\+[1-9][0-9]{6,14}$'
  flags: ""                             # i, m, s combos
```

Patterns are evaluated by the source engine (Postgres regex on the SQL
path; Java/Scala regex on the Spark path). Use POSIX-compatible
patterns when possible.

---

## range — *stable*

Fail rows whose column is outside the inclusive range.

```yaml
type: range
config:
  column: discount_pct
  min: 0
  max: 100
```

Either bound is optional.

---

## freshness — *experimental* (v0.2)

Fail the *whole rule* (not per row) if `max(timestamp_column)` is older
than the configured age. Score is binary: `1.0` if fresh, `0.0` if not.

```yaml
type: freshness
config:
  column: updated_at
  max_age: "24h"                        # 30m, 24h, 7d
```

Status: present in code; not exercised in tests in v0.1.

---

## custom_sql — *experimental* (v0.2)

Run a custom `SELECT … FROM <dataset>` that must return one row with
columns `total`, `failed`, and optionally `sample` (a JSON array of
failing-row identifiers).

```yaml
type: custom_sql
config:
  sql: |
    SELECT
      count(*)               AS total,
      count(*) FILTER (
        WHERE shipped_at < ordered_at
      )                       AS failed
    FROM {dataset}
```

`{dataset}` is substituted with the bound table reference. Only `SELECT`
is allowed; the connector enforces read-only mode. Status:
experimental, behind `ENABLE_CUSTOM_SQL_RULES=false` by default. Treat
custom SQL as you would treat any user-supplied SQL — it can express
expensive queries.

---

## Choosing a rule type

| Question | Use |
|---|---|
| "Is this column never null?" | `completeness` |
| "Are the values unique?" | `uniqueness` |
| "Is this a valid email/URL/UUID/IP/date?" | `validity` |
| "Does this value match a pattern?" | `regex` |
| "Is the value one of a small set?" | `accepted_values` |
| "Is the number within bounds?" | `range` (interval) or `comparison` (single bound) |
| "Does column A relate correctly to column B / dataset B?" | `consistency` |
| "Is this dataset still being updated?" | `freshness` |
| "I have a complex business rule." | `custom_sql` (experimental) |

If your check does not fit any of the above, please open a feature
request — we want the standard library to grow.

---

## Authoring rules programmatically

Beyond the UI, you can create rules via the API. See
[api-reference.md](api-reference.md). Example rule documents in
`examples/rules/` are designed to be POSTed as-is.
