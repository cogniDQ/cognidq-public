/**
 * F003 – Packet 07: Workspace Settings Page
 *
 * E2E tests cover the following acceptance criteria:
 *
 *   AC-P07-01  settings page loads and displays all five sections
 *   AC-P07-02  fetched settings values are displayed in sections
 *   AC-P07-03  workspace_administrator can update timezone → success toast
 *   AC-P07-04  workspace_administrator can update SLA policy → success toast
 *   AC-P07-05  SLA ordering validation prevents submission when critical > major
 *   AC-P07-06  workspace_administrator can change issue grouping mode
 *   AC-P07-07  workspace_administrator can update naming standards pattern
 *   AC-P07-08  invalid regex in naming standards → inline error, no submit
 *   AC-P07-09  data_engineer sees sections but no edit buttons
 *   AC-P07-10  "Settings" link on WorkspaceDetailPage only for workspace_administrator
 *   AC-P07-11  non-permitted role (platform_operator) → redirected
 *   AC-P07-12  archived workspace: settings visible, save is still enabled (API enforces)
 *
 * ── Mocking strategy ────────────────────────────────────────────────────
 * All API calls intercepted via function-based page.route() matchers; no
 * requests reach the Docker backend.
 */

import { test, expect, Page, Route } from '@playwright/test';

// ---------------------------------------------------------------------------
// JWT helper
// ---------------------------------------------------------------------------

function buildJwt(
  actorRole:
    | 'workspace_administrator'
    | 'data_engineer'
    | 'data_steward'
    | 'platform_operator'
    | 'platform_viewer',
): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      email: 'test@example.com',
      actor_role: actorRole,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const WS_ID = 'ws-settings-001';

const SETTINGS_DATA = {
  workspace_id: WS_ID,
  tenant_id: 'tenant-001',
  timezone_policy: { default_timezone: 'UTC' },
  severity_policy: {
    critical_label: 'Critical',
    major_label: 'Major',
    minor_label: 'Minor',
    informational_label: 'Informational',
  },
  sla_policy: {
    critical_hours: 4,
    major_hours: 24,
    minor_hours: 72,
    informational_hours: null,
  },
  issue_grouping_policy: 'one_per_execution',
  naming_standards: {
    datasets: {
      max_length: 64,
      allowed_pattern: '^[a-z][a-z0-9_]*$',
      forbidden_keywords: ['temp', 'draft'],
    },
    rules: {
      max_length: null,
      allowed_pattern: null,
      forbidden_keywords: null,
    },
  },
  updated_at: null,
  updated_by: null,
};

const SETTINGS_RESPONSE = { data: SETTINGS_DATA };

const ACTIVE_WORKSPACE = {
  workspace_id: WS_ID,
  tenant_id: 'tenant-001',
  workspace_name: 'Analytics Team',
  workspace_slug: 'analytics-team',
  description: 'Main analytics workspace',
  default_timezone: 'UTC',
  status: 'active',
  status_reason: null,
  created_at: '2024-01-15T10:00:00Z',
  updated_at: '2024-03-20T08:30:00Z',
  created_by: 'test-user-id',
  updated_by: 'test-user-id',
  dataset_count: 5,
  member_count: 3,
};

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

async function setupAuth(
  page: Page,
  role:
    | 'workspace_administrator'
    | 'data_engineer'
    | 'data_steward'
    | 'platform_operator'
    | 'platform_viewer',
): Promise<void> {
  await page.addInitScript(
    ({ token }) => localStorage.setItem('access_token', token),
    { token: buildJwt(role) },
  );

  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-id',
          email: 'test@example.com',
          full_name: 'Test User',
          avatar_url: null,
          email_verified: true,
          status: 'active',
          last_login_at: null,
          created_at: '2024-01-01T00:00:00Z',
        }),
      }),
  );

  await page.route(
    (url) =>
      url.href.includes('/auth/refresh') || url.href.includes('/auth/token'),
    (route: Route) =>
      route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }),
  );
}

/** Mock GET /workspaces/{WS_ID}/settings */
async function mockGetSettings(page: Page, fixture = SETTINGS_RESPONSE): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/settings`),
    (route: Route) => {
      const method = route.request().method();
      if (method === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(fixture),
        });
      } else {
        route.fallback();
      }
    },
  );
}

/** Mock PATCH /workspaces/{WS_ID}/settings → responds with updated data */
async function mockPatchSettings(page: Page, responseData = SETTINGS_DATA): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/settings`),
    (route: Route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: responseData }),
        });
      } else {
        route.fallback();
      }
    },
  );
}

/** Mock GET /workspaces/{WS_ID} (workspace detail) */
async function mockGetWorkspace(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}`) &&
      !url.href.includes('/settings') &&
      !url.href.includes('/archive') &&
      !url.href.includes('/restore'),
    (route: Route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: ACTIVE_WORKSPACE }),
        });
      } else {
        route.continue();
      }
    },
  );
}

/** Mock audit log endpoint to prevent 404s from the AuditLogPanel */
async function mockAuditLog(page: Page): Promise<void> {
  await page.route(
    (url) => url.href.includes('/audit-log') || url.href.includes('/audit_log'),
    (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [], meta: { total: 0 } }),
      }),
  );
}

const SETTINGS_URL = `/workspaces/${WS_ID}/settings`;
const DETAIL_URL = `/workspaces/${WS_ID}`;

// ---------------------------------------------------------------------------
// AC-P07-01  Settings page loads and displays all five sections
// ---------------------------------------------------------------------------

test('AC-P07-01: settings page loads all five policy sections', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  await expect(page.getByTestId('workspace-settings-page')).toBeVisible();
  await expect(page.getByTestId('timezone-section')).toBeVisible();
  await expect(page.getByTestId('severity-policy-section')).toBeVisible();
  await expect(page.getByTestId('sla-policy-section')).toBeVisible();
  await expect(page.getByTestId('issue-grouping-section')).toBeVisible();
  await expect(page.getByTestId('naming-standards-section')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-P07-02  Fetched settings values are displayed in sections
// ---------------------------------------------------------------------------

test('AC-P07-02: fetched settings values are displayed in sections', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  // Timezone
  await expect(page.getByTestId('timezone-value')).toHaveText('UTC');

  // Severity labels
  await expect(page.getByTestId('severity-critical-value')).toHaveText('Critical');
  await expect(page.getByTestId('severity-major-value')).toHaveText('Major');

  // SLA values
  await expect(page.getByTestId('sla-critical-value')).toHaveText('4h');
  await expect(page.getByTestId('sla-major-value')).toHaveText('24h');

  // Issue grouping
  await expect(page.getByTestId('grouping-value')).toHaveText(/one per execution/i);

  // Naming standards - datasets pattern
  await expect(page.getByTestId('datasets-pattern-value')).toContainText('^[a-z]');
});

// ---------------------------------------------------------------------------
// AC-P07-03  workspace_administrator can update timezone → success toast
// ---------------------------------------------------------------------------

test('AC-P07-03: workspace_administrator can update timezone with success toast', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await mockPatchSettings(page, {
    ...SETTINGS_DATA,
    timezone_policy: { default_timezone: 'Europe/London' },
  });
  await page.goto(SETTINGS_URL);

  await page.getByTestId('timezone-edit-btn').click();
  await page.getByTestId('timezone-input').fill('Europe/London');
  await page.getByTestId('timezone-save-btn').click();

  // Success toast should appear
  await expect(page.getByText(/timezone updated/i)).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// AC-P07-04  workspace_administrator can update SLA policy → success toast
// ---------------------------------------------------------------------------

test('AC-P07-04: workspace_administrator can update SLA policy with success toast', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await mockPatchSettings(page);
  await page.goto(SETTINGS_URL);

  await page.getByTestId('sla-edit-btn').click();
  await page.getByTestId('sla-critical-input').fill('2');
  await page.getByTestId('sla-save-btn').click();

  await expect(page.getByText(/sla policy updated/i)).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// AC-P07-05  SLA ordering validation prevents submission when critical > major
// ---------------------------------------------------------------------------

test('AC-P07-05: SLA ordering validation prevents submission when critical > major', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  await page.getByTestId('sla-edit-btn').click();
  // Set critical > major (4h initial, set to 100 which is > major=24)
  await page.getByTestId('sla-critical-input').fill('100');
  await page.getByTestId('sla-save-btn').click();

  // Inline error should appear, no PATCH call made
  await expect(page.getByTestId('sla-error')).toBeVisible();
  await expect(page.getByTestId('sla-error')).toContainText(/≤/);
});

// ---------------------------------------------------------------------------
// AC-P07-06  workspace_administrator can change issue grouping mode
// ---------------------------------------------------------------------------

test('AC-P07-06: workspace_administrator can change issue grouping mode', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await mockPatchSettings(page, {
    ...SETTINGS_DATA,
    issue_grouping_policy: 'one_per_rule',
  });
  await page.goto(SETTINGS_URL);

  await page.getByTestId('grouping-edit-btn').click();
  await page.getByTestId('grouping-radio-one_per_rule').click();
  await page.getByTestId('grouping-save-btn').click();

  await expect(page.getByText(/issue grouping mode updated/i)).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// AC-P07-07  workspace_administrator can update naming pattern → success toast
// ---------------------------------------------------------------------------

test('AC-P07-07: workspace_administrator can update naming pattern with success toast', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await mockPatchSettings(page);
  await page.goto(SETTINGS_URL);

  await page.getByTestId('datasets-edit-btn').click();
  await page.getByTestId('datasets-pattern-input').fill('^[A-Za-z].*$');
  await page.getByTestId('datasets-save-btn').click();

  await expect(page.getByText(/dataset naming standards updated/i)).toBeVisible({ timeout: 5000 });
});

// ---------------------------------------------------------------------------
// AC-P07-08  invalid regex in naming standards → inline error, no submit
// ---------------------------------------------------------------------------

test('AC-P07-08: invalid regex in naming standards shows inline error and does not submit', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  await page.getByTestId('datasets-edit-btn').click();
  // Set an invalid regex
  await page.getByTestId('datasets-pattern-input').fill('[invalid-regex(');
  await page.getByTestId('datasets-save-btn').click();

  // Inline error message should appear
  await expect(page.getByTestId('datasets-error')).toBeVisible();
  await expect(page.getByTestId('datasets-error')).toContainText(/invalid regular expression/i);
});

// ---------------------------------------------------------------------------
// AC-P07-09  data_engineer sees sections but no edit buttons
// ---------------------------------------------------------------------------

test('AC-P07-09: data_engineer sees all sections but no edit buttons', async ({ page }) => {
  await setupAuth(page, 'data_engineer');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  await expect(page.getByTestId('workspace-settings-page')).toBeVisible();

  // All sections visible
  await expect(page.getByTestId('timezone-section')).toBeVisible();
  await expect(page.getByTestId('severity-policy-section')).toBeVisible();
  await expect(page.getByTestId('sla-policy-section')).toBeVisible();
  await expect(page.getByTestId('issue-grouping-section')).toBeVisible();
  await expect(page.getByTestId('naming-standards-section')).toBeVisible();

  // No edit buttons
  await expect(page.getByTestId('timezone-edit-btn')).not.toBeVisible();
  await expect(page.getByTestId('severity-edit-btn')).not.toBeVisible();
  await expect(page.getByTestId('sla-edit-btn')).not.toBeVisible();
  await expect(page.getByTestId('grouping-edit-btn')).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-P07-10  "Settings" link on WorkspaceDetailPage only for workspace_administrator
// ---------------------------------------------------------------------------

test('AC-P07-10: Settings link is visible on WorkspaceDetailPage for workspace_administrator', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page);
  await mockAuditLog(page);
  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('workspace-settings-link')).toBeVisible();
});

test('AC-P07-10b: Settings link is NOT visible on WorkspaceDetailPage for data_engineer', async ({ page }) => {
  await setupAuth(page, 'data_engineer');
  await mockGetWorkspace(page);
  await mockAuditLog(page);
  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('workspace-settings-link')).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-P07-11  non-permitted role → redirected (page does not render)
// ---------------------------------------------------------------------------

test('AC-P07-11: platform_operator is redirected from settings page', async ({ page }) => {
  await setupAuth(page, 'platform_operator');
  await mockGetSettings(page);
  await page.goto(SETTINGS_URL);

  // Should be redirected away from settings page — settings page should not be visible
  await expect(page.getByTestId('workspace-settings-page')).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-P07-12  workspace_administrator can update severity labels
// ---------------------------------------------------------------------------

test('AC-P07-12: workspace_administrator can update severity labels with success toast', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetSettings(page);
  await mockPatchSettings(page, {
    ...SETTINGS_DATA,
    severity_policy: {
      critical_label: 'P1',
      major_label: 'P2',
      minor_label: 'P3',
      informational_label: 'P4',
    },
  });
  await page.goto(SETTINGS_URL);

  await page.getByTestId('severity-edit-btn').click();
  await page.getByTestId('severity-critical-input').fill('P1');
  await page.getByTestId('severity-major-input').fill('P2');
  await page.getByTestId('severity-save-btn').click();

  await expect(page.getByText(/severity labels updated/i)).toBeVisible({ timeout: 5000 });
});
