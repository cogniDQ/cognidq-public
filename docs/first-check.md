# Your first data quality check

This guide walks you through the canonical CogniDQ flow:

1. log in
2. open the demo workspace
3. create a rule on a sample dataset
4. run it
5. read the result, see failed rows
6. open an issue
7. see the dashboard update

Prerequisite: the local stack is running and seeded — see
[getting-started.md](getting-started.md).

---

## 1. Log in

Open <http://localhost:5173> and sign in as **data steward**:

- email: `steward@example.com`
- password: `change-me-strong-password`

The data steward role is the right level of access for authoring rules
and triaging issues.

## 2. Pick the workspace

After login you land on the workspace selector. Pick **Demo Workspace**
(seeded by `make seed`). The workspace ships with three sample
datasets:

- `customers` — synthetic customer records (~5 000 rows)
- `orders` — synthetic orders (~30 000 rows)
- `payments` — synthetic payments (~25 000 rows)

Each contains intentional quality issues — null emails, duplicate IDs,
negative amounts — so the demo always has something to find.

## 3. Create a rule

Click **Rules → New rule**. Fill in:

| Field | Value |
|---|---|
| Name | `customers.email is not null` |
| Dataset | `customers` |
| Rule type | `completeness` |
| Column | `email` |
| Threshold | `pass if score ≥ 99%` |
| Severity | `medium` |

Save. The rule appears in the list with status `not yet executed`.

## 4. Run it

Click the rule, then **Run now**. The execution is dispatched to the
worker. Within a few seconds you should see:

- status: `failed` (because the seed dataset has ~3% missing emails)
- score: about `0.97`
- failed rows: about `150`
- duration: under a second on the seed dataset

## 5. Inspect failed rows

Click the execution to open the result page. The **Evidence** tab shows
a sample of failing rows (default: first 100). Each row includes:

- a stable row reference (primary key, when available)
- the column values relevant to the rule
- a timestamp

Evidence is stored in MinIO at
`minio://dq-data-assets/evidence/<workspace>/<execution-id>.json`.
You can browse the bucket at <http://localhost:9001>.

## 6. Open an issue

The execution page shows a banner: "1 issue auto-created from this
failure". Click it. The issue inherits:

- title: `customers.email is not null — failed`
- severity: `medium` (from the rule)
- status: `open`
- assignee: empty

Assign it to yourself, add a comment, and change status to
`in progress`.

## 7. (Optional) Group into an incident

Run two more rules that exercise the same dataset:

- `customers.country in ['US','UK','FR','DE','IT','ES']`
  (rule type: `accepted_values`)
- `customers.id is unique` (rule type: `uniqueness`)

Both will fail. From the **Issues** page, select the three issues and
click **Group as incident**. Set:

- title: `Customer-data quality regression`
- severity: `high`
- workspace owner: yourself

The dashboard incident counter goes from 0 to 1.

## 8. Read the dashboard

Navigate to **Dashboard**. You should see:

- workspace health score around `0.7` (depending on which rules ran)
- 3 failing rules
- 1 incident
- recent execution timeline

## 9. Schedule a recurring check

Go back to the first rule. Open **Schedule**. Pick "every 5 minutes" for
the demo. The rule now runs on the Celery Beat schedule. You can watch
new executions land in real time on the rule page.

## What you have just used

A complete, working data quality control plane:

- rule authoring with schema-aware fields
- on-demand and scheduled execution
- failed-row evidence
- issue + incident workflow
- workspace-level metrics

For deeper concepts see:

- [rule-engine.md](rule-engine.md)
- [rule-types.md](rule-types.md)
- [issues.md](issues.md), [incidents.md](incidents.md),
  [evidence.md](evidence.md)
- [rbac.md](rbac.md)
