# Demo walkthrough

A 10-minute, scripted tour of CogniDQ. Use this to demo the project
to teammates or in a screencast.

Prerequisite: local stack running and seeded
([getting-started.md](getting-started.md)).

---

## Cast of characters

The seed loader creates these users (all with password
`change-me-strong-password`):

- `admin@example.com` — platform admin
- `tenant.admin@example.com` — tenant admin
- `ws.admin@example.com` — workspace administrator
- `engineer@example.com` — data engineer
- `steward@example.com` — data steward (most demos use this)
- `analyst@example.com` — business analyst
- `viewer@example.com` — governance viewer

## Scene 1 — "What does CogniDQ do?" (1 min)

1. Sign in as `admin@example.com`. Show the platform admin landing
   page: tenants, system info, version (`/api/v1/system/version`).
2. Switch scope to **Acme Corp → Demo Workspace**.

> Talking point: "CogniDQ is a control plane for data quality.
> Connections, datasets, rules, executions, issues. Multi-tenant from
> the start."

## Scene 2 — Browse a dataset (1 min)

1. Open **Datasets → customers**.
2. Show the field list, the sample preview (50 rows), and the field
   stats panel: null %, distinct count, sample values.

> Talking point: "Schema is inferred from the source. We never read
> more than a bounded preview; full table scans only happen during a
> rule execution."

## Scene 3 — Run an existing rule (2 min)

1. Open **Rules**. Show the seeded rules:
   - `customers.email is not null` (completeness)
   - `customers.country in [...]` (accepted_values)
   - `orders.amount >= 0` (range)
   - `payments.transaction_id is unique` (uniqueness)
2. Click **Run all**.
3. While they execute (~10 s), open **Executions** and show the live
   list updating.
4. When they finish, point at one that failed. Open it.
5. Show the **Evidence** tab — the sample of failing rows.

> Talking point: "Failed rule → execution record + evidence sample.
> The sample is bounded; we don't pull the whole failed-rows set."

## Scene 4 — Triage an issue (2 min)

1. From the execution page, click "1 issue auto-created".
2. On the issue page:
   - assign yourself,
   - change status to `in_progress`,
   - add a comment "looking into it",
   - look at the timeline updating live.

> Talking point: "Issues are one per rule, not one per run. Recurring
> failures append to the same issue."

## Scene 5 — Group into an incident (1 min)

1. Go back to **Issues**. Select two or three failing-rule issues.
2. Click **Group as incident**, set:
   - title: `Customer-data quality regression`
   - severity: `high`.
3. Show the incident page: linked issues, single owner, status.

> Talking point: "When multiple issues share a root cause, group them
> as an incident so stakeholders track one thing."

## Scene 6 — Author a new rule (2 min)

1. **Rules → New rule**. Pick `orders` dataset.
2. Type: `consistency`. Config:
   - left: `shipped_at`
   - right: `ordered_at`
   - operator: `>=`
3. Threshold: `score >= 0.99`. Severity: `high`. Save.
4. Click **Run now**. It fails (some seeded orders ship before they're
   ordered).
5. Open evidence; point at the row references.

> Talking point: "Rules are versioned. Editing a rule creates a new
> version; old executions reference the old version forever."

## Scene 7 — Schedule (30 s)

1. On the rule, open **Schedule**, pick "every 5 minutes".
2. Show the schedule appears on the rule list.

> Talking point: "Beat enqueues; workers execute. Single-instance Beat,
> N workers — standard Celery topology."

## Scene 8 — Dashboard (1 min)

1. **Dashboard**. Show:
   - workspace health score,
   - failing rules count,
   - open issues by severity,
   - executions over time.
2. Hover the trend chart to show drill-downs.

> Talking point: "Dashboards are read-only views over the same data
> the rest of the app uses; nothing pre-aggregated yet — that lands in
> v0.2."

## Scene 9 — RBAC (30 s)

1. Sign out. Sign in as `analyst@example.com`.
2. Try to edit a rule — buttons are absent.
3. Show that the analyst can comment on issues but not change their
   status.

> Talking point: "Backend is the source of truth for RBAC. The frontend
> hides UI; the backend enforces."

## Scene 10 — Audit (30 s)

1. Sign in as `viewer@example.com` (governance_viewer).
2. Open **Audit log**. Show the events from earlier in the demo:
   `rule.run`, `issue.update`, `incident.create`, `evidence.read`.

> Talking point: "Append-only audit trail at the application layer.
> Production should additionally harden the DB so audit rows can't be
> mutated."

## Scene 11 — What we did NOT show (closing)

- Source-system writebacks. CogniDQ doesn't do them.
- Real-time streaming. Execution is batch.
- A catalog. We integrate; we don't replace.
- Custom SQL rules. Available behind a feature flag; off by default.

> Closing line: "Apache-2.0, multi-tenant, batteries-included for the
> demo, opinionated about what's in scope. Code at
> github.com/cogniDQ/cognidq-public."

---

## Reset between demos

```bash
make reset
docker compose up -d
make migrate seed
```

## Recording tips

- 1280×800 viewport is enough; the UI adapts.
- Open in incognito to avoid cached login state from previous demos.
- Keep a terminal visible for `make logs` so the audience sees workers
  pick up tasks.
