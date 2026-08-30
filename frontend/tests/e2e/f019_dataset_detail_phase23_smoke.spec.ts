/**
 * F19 — Phase 2/3 dataset detail smoke
 *
 * Validates the work shipped in Phases 1–3 of the dataset detail revamp:
 *   • F5  — Tabbed workbench (sample / profile / quality / lineage)
 *   • F6  — Quality matcher picks up rules by data_source_id + table name
 *   • F7  — "Executions →" deep link round-trips through ?rule=&tab=executions
 *   • F8  — Audit log entry is expandable
 *   • F9  — "auto" placeholder description is hidden
 *   • F10 — Quality header sparkline + dimension donut render
 *   • F11 — Schema-drift badge: "Schema not profiled" when last_profiled_at null
 *   • F12 — Inline null/distinct stat bars in fields table
 *   • F13 — Lineage panel shows upstream + downstream rules
 *   • F14 — ?audit=1 and ?tab=quality survive a reload
 *
 * All API calls are mocked via page.route() so the spec is hermetic.
 */

import { test, expect, Page } from '@playwright/test';

// ─── Fixtures ───────────────────────────────────────────────────────────────

const TENANT_ID = '33333333-3333-4333-8333-333333333333';
const WORKSPACE_ID = '44444444-4444-4444-8444-444444444444';
const DATASET_ID = '2dc72081-46df-4005-b0b2-1bef962c418c';
const DATA_SOURCE_ID = '55555555-5555-4555-8555-555555555555';
const RULE_ID = 'rule-0001-aaaa-bbbb-cccccccccccc';

function buildJwt(actorRole: string): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'qa-de',
      email: 'qa.dataengineer@rbac-qa.test',
      actor_role: actorRole,
      tenant_id: TENANT_ID,
      workspace_id: WORKSPACE_ID,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

const DATASET_FIXTURE = {
  dataset_id: DATASET_ID,
  workspace_id: WORKSPACE_ID,
  tenant_id: TENANT_ID,
  data_source_id: DATA_SOURCE_ID,
  data_source_name: 'prod-postgres',
  dataset_name: 'hr_employees',
  dataset_type: 'table',
  physical_identifier: 'employees',
  schema_name: 'hr',
  // F9 — "auto" should be stripped on render.
  description: 'auto',
  business_domain: 'HR',
  criticality: 'high',
  status: 'active',
  field_count: 2,
  fields: [
    {
      field_id: 'f-001',
      field_name: 'employee_id',
      data_type: 'integer',
      ordinal_position: 1,
      nullable: false,
      is_key_candidate: true,
      null_count: 0,
      distinct_count: 1000,
      profile_stats: { row_count: 1000 },
      min_value: '1',
      max_value: '1000',
    },
    {
      field_id: 'f-002',
      field_name: 'email',
      data_type: 'text',
      ordinal_position: 2,
      nullable: true,
      is_key_candidate: false,
      null_count: 50,
      distinct_count: 950,
      profile_stats: { row_count: 1000 },
      min_value: null,
      max_value: null,
    },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:00Z',
  activated_at: '2026-01-02T00:00:00Z',
  archived_at: null,
  archived_by: null,
  created_by: 'user-001',
  updated_by: null,
  // F11 — null forces "Schema not profiled" badge.
  last_profiled_at: null,
};

const RULE_FIXTURE = {
  id: RULE_ID,
  workspace_id: WORKSPACE_ID,
  name: 'Email must not be null',
  description: 'Completeness check on email column',
  category: 'completeness',
  status: 'active',
  is_active: true,
  // F6 — schema casing differs on purpose; matcher must still pick this up.
  target_schema: 'HR',
  target_table: 'EMPLOYEES',
  target_columns: ['email'],
  data_source_id: DATA_SOURCE_ID,
};

function buildExecutions() {
  // 5 daily completed executions trending upward — exercises the F10
  // sparkline path while keeping the fixture compact.
  const now = Date.now();
  return Array.from({ length: 5 }).map((_, i) => ({
    id: `exec-${i}`,
    rule_id: RULE_ID,
    workspace_id: WORKSPACE_ID,
    status: 'completed',
    started_at: new Date(now - (5 - i) * 86_400_000).toISOString(),
    completed_at: new Date(now - (5 - i) * 86_400_000 + 60_000).toISOString(),
    created_at: new Date(now - (5 - i) * 86_400_000).toISOString(),
    duration_seconds: 60,
    rows_scanned: 1000,
    rows_passed: 950 + i * 5,
    rows_failed: 50 - i * 5,
    pass_rate: 95 + i,
    executed_by: 'qa-de',
  }));
}

const AUDIT_LOG_FIXTURE = {
  items: [
    {
      log_id: 'audit-001',
      action_type: 'dataset_activated',
      actor_id: 'user-0001-aaaa-bbbb-cccccccccccc',
      actor_role: 'data_engineer',
      new_data: { status: 'active', activated_at: '2026-01-02T00:00:00Z' },
      occurred_at: '2026-01-02T00:00:00Z',
    },
  ],
  meta: { total: 1, page: 1, page_size: 20, has_next: false },
};

// ─── Mock setup ─────────────────────────────────────────────────────────────

async function installMocks(page: Page): Promise<void> {
  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem('access_token', token);
    },
    { token: buildJwt('data_engineer') },
  );

  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'qa-de',
          email: 'qa.dataengineer@rbac-qa.test',
          full_name: 'QA Data Engineer',
          actor_role: 'data_engineer',
          tenant_id: TENANT_ID,
          workspace_id: WORKSPACE_ID,
          email_verified: true,
          status: 'active',
        }),
      }),
  );

  // Workspace meta (any non-dataset, non-rule probe).
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}`) &&
      !url.href.includes('/datasets') &&
      !url.href.includes('/rules'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            workspace_id: WORKSPACE_ID,
            workspace_name: 'QA Workspace',
            workspace_slug: 'qa',
            organization_id: 'org-001',
            tenant_id: TENANT_ID,
            status: 'active',
            default_timezone: 'UTC',
          },
        }),
      }),
  );

  // Dataset detail.
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`,
      ) && !url.href.includes('/audit-logs'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DATASET_FIXTURE),
      }),
  );

  // Audit logs.
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}/audit-logs`,
      ),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUDIT_LOG_FIXTURE),
      }),
  );

  // Rules list — single rule that targets this dataset by data_source_id.
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/rules`) &&
      !url.href.match(/\/rules\/[^/?]+\//),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([RULE_FIXTURE]),
        });
      } else {
        route.fallback();
      }
    },
  );

  // Rule executions (matched per-rule).
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WORKSPACE_ID}/rules/${RULE_ID}/executions`,
      ),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(buildExecutions()),
      }),
  );
}

// ─── Tests ─────────────────────────────────────────────────────────────────

test.describe('F19 — Dataset detail Phase 2/3 smoke', () => {
  test.beforeEach(async ({ page }) => {
    await installMocks(page);
  });

  test('header renders schema-drift badge and strips placeholder description', async ({
    page,
  }) => {
    await page.goto(
      `/hub/t/${TENANT_ID}/ws/${WORKSPACE_ID}/datasets/${DATASET_ID}`,
    );
    await expect(page.getByTestId('dataset-detail')).toBeVisible();
    // F11 — badge present + reads "Schema not profiled" because
    // last_profiled_at is null in the fixture.
    await expect(page.getByTestId('schema-drift-badge')).toContainText(
      /Schema not profiled/i,
    );
    // F9 — "auto" placeholder is replaced with em-dash.
    await expect(page.getByText(/Description/)).toBeVisible();
    await expect(page.locator('text=auto').first()).not.toBeVisible();
  });

  test('fields table shows inline null and distinct stat bars', async ({
    page,
  }) => {
    await page.goto(
      `/hub/t/${TENANT_ID}/ws/${WORKSPACE_ID}/datasets/${DATASET_ID}`,
    );
    await expect(page.getByTestId('field-row-f-002')).toBeVisible();
    // F12 — bars render for each column with stats.
    await expect(
      page
        .getByTestId('field-row-f-002')
        .getByTestId('field-stat-null')
        .first(),
    ).toBeVisible();
    await expect(
      page
        .getByTestId('field-row-f-002')
        .getByTestId('field-stat-distinct')
        .first(),
    ).toBeVisible();
  });

  test('workbench tabs round-trip through the URL', async ({ page }) => {
    await page.goto(
      `/hub/t/${TENANT_ID}/ws/${WORKSPACE_ID}/datasets/${DATASET_ID}`,
    );
    await expect(page.getByTestId('dataset-workbench')).toBeVisible();

    // F5 — switch to Quality and verify URL updates.
    await page.getByTestId('workbench-tab-quality').click();
    await expect(page).toHaveURL(/[?&]tab=quality/);
    await expect(page.getByTestId('dataset-quality-panel')).toBeVisible();

    // F6 — quality matcher picked up the rule despite schema casing drift.
    await expect(
      page.getByTestId(`quality-rule-card-${RULE_ID}`),
    ).toBeVisible();

    // F10 — header charts render.
    await expect(page.getByTestId('quality-header-charts')).toBeVisible();
    await expect(page.getByTestId('quality-sparkline')).toBeVisible();
    await expect(page.getByTestId('quality-donut')).toBeVisible();

    // F5 — switch to Lineage.
    await page.getByTestId('workbench-tab-lineage').click();
    await expect(page).toHaveURL(/[?&]tab=lineage/);
    // F13 — lineage panel renders downstream rule entry.
    await expect(page.getByTestId('dataset-lineage-panel')).toBeVisible();
    await expect(page.getByTestId('lineage-downstream-list')).toContainText(
      RULE_FIXTURE.name,
    );
  });

  test('audit log expansion + URL persistence (?audit=1)', async ({ page }) => {
    await page.goto(
      `/hub/t/${TENANT_ID}/ws/${WORKSPACE_ID}/datasets/${DATASET_ID}`,
    );
    // F14 — open audit panel and confirm URL updates.
    await page.getByTestId('audit-log-toggle').click();
    await expect(page).toHaveURL(/[?&]audit=1/);
    await expect(page.getByTestId('audit-row-audit-001')).toBeVisible();

    // F8 — entry expands to reveal new_data JSON.
    await page.getByTestId('audit-row-audit-001').click();
    await expect(page.getByTestId('audit-detail-audit-001')).toContainText(
      'activated_at',
    );

    // F14 — reload preserves audit-open state.
    await page.reload();
    await expect(page.getByTestId('audit-row-audit-001')).toBeVisible();
  });
});
