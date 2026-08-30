/**
 * F031 — Packet 5: Frontend Issues List Page
 *
 * E2E tests cover the primary user flows:
 *
 *   E2E-01  Issues list page loads showing existing issues
 *   E2E-02  Empty state shown when no issues exist
 *   E2E-03  Status filter dropdown updates results
 *   E2E-04  Severity filter dropdown updates results
 *   E2E-05  Pagination: next/previous buttons work
 *   E2E-06  SeverityBadge renders correct colour for critical
 *   E2E-07  Overdue due_at renders in red
 *   E2E-08  Workspace detail quick link navigates to issues page
 *
 * Mocking strategy: JWT in localStorage, all API calls intercepted via page.route()
 */

import { test, expect, Page } from '@playwright/test';

// ────────────────────────────────────────────────────────────────────────────
// JWT helper
// ────────────────────────────────────────────────────────────────────────────

function buildJwt(actorRole: string): string {
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

// ────────────────────────────────────────────────────────────────────────────
// Fixtures
// ────────────────────────────────────────────────────────────────────────────

const WORKSPACE_ID = 'ws-test-f031';

const ISSUE_1 = {
  id: 'iss-001',
  workspace_id: WORKSPACE_ID,
  issue_type: 'threshold_breach',
  severity: 'critical',
  status: 'open',
  title: '[CRITICAL] Check failed: node n1',
  impact_summary: '150 of 1000 rows failed (85.0% pass rate)',
  failure_count: 150,
  due_at: '2020-01-01T00:00:00Z',  // overdue
  opened_at: new Date(Date.now() - 3_600_000).toISOString(),
};

const ISSUE_2 = {
  id: 'iss-002',
  workspace_id: WORKSPACE_ID,
  issue_type: 'threshold_breach',
  severity: 'minor',
  status: 'resolved',
  title: '[MINOR] Check failed: node n2',
  impact_summary: '5 of 500 rows failed (99.0% pass rate)',
  failure_count: 5,
  due_at: null,
  opened_at: new Date(Date.now() - 86_400_000).toISOString(),
};

const ISSUES_PAGE_1 = {
  items: [ISSUE_1, ISSUE_2],
  total: 3,
  page: 1,
  page_size: 25,
  has_next: true,
};

const ISSUES_PAGE_2 = {
  items: [{
    ...ISSUE_1,
    id: 'iss-003',
    title: '[CRITICAL] Check failed: node n3',
  }],
  total: 3,
  page: 2,
  page_size: 25,
  has_next: false,
};

const EMPTY_PAGE = {
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
  has_next: false,
};

const WORKSPACE_FIXTURE = {
  workspace_id: WORKSPACE_ID,
  workspace_name: 'Test Workspace',
  workspace_slug: 'test-ws',
  status: 'active',
  tenant_id: 'tenant-001',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  dataset_count: 5,
  member_count: 2,
};

// ────────────────────────────────────────────────────────────────────────────
// Setup
// ────────────────────────────────────────────────────────────────────────────

async function setupAuth(page: Page) {
  await page.addInitScript(() => {
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const payload = btoa(
      JSON.stringify({
        sub: 'test-user-id',
        email: 'test@example.com',
        actor_role: 'workspace_administrator',
        exp: Math.floor(Date.now() / 1000) + 3600,
      }),
    );
    localStorage.setItem('access_token', `${header}.${payload}.fakesig`);
  });
}

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F031 P05 — Issues List Page', () => {

  // E2E-01: Issues list page loads showing existing issues
  test('E2E-01: issues list page loads with issues', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ISSUES_PAGE_1) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    await expect(page.getByText('Issues')).toBeVisible();
    await expect(page.getByTestId('issue-card')).toHaveCount(2);
    await expect(page.getByText('[CRITICAL] Check failed: node n1')).toBeVisible();
  });

  // E2E-02: Empty state shown when no issues
  test('E2E-02: empty state when no issues', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EMPTY_PAGE) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    await expect(page.getByTestId('issues-empty')).toBeVisible();
    await expect(page.getByText('No issues found.')).toBeVisible();
  });

  // E2E-03: Status filter updates results
  test('E2E-03: status filter updates results', async ({ page }) => {
    await setupAuth(page);
    let lastUrl = '';
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      lastUrl = route.request().url();
      const isFiltered = lastUrl.includes('status=open');
      const body = isFiltered
        ? { items: [ISSUE_1], total: 1, page: 1, page_size: 25, has_next: false }
        : ISSUES_PAGE_1;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    await expect(page.getByTestId('issue-card')).toHaveCount(2);

    await page.getByTestId('status-filter').selectOption('open');
    await expect(page.getByTestId('issue-card')).toHaveCount(1);
  });

  // E2E-04: Severity filter updates results
  test('E2E-04: severity filter updates results', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      const url = route.request().url();
      const isFiltered = url.includes('severity=critical');
      const body = isFiltered
        ? { items: [ISSUE_1], total: 1, page: 1, page_size: 25, has_next: false }
        : ISSUES_PAGE_1;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    await expect(page.getByTestId('issue-card')).toHaveCount(2);

    await page.getByTestId('severity-filter').selectOption('critical');
    await expect(page.getByTestId('issue-card')).toHaveCount(1);
  });

  // E2E-05: Pagination next/previous
  test('E2E-05: pagination next and previous', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      const url = route.request().url();
      const body = url.includes('page=2') ? ISSUES_PAGE_2 : ISSUES_PAGE_1;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    await expect(page.getByTestId('issue-card')).toHaveCount(2);

    // Click next
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(page.getByTestId('issue-card')).toHaveCount(1);
    await expect(page.getByText('[CRITICAL] Check failed: node n3')).toBeVisible();

    // Click previous
    await page.getByRole('button', { name: 'Previous' }).click();
    await expect(page.getByTestId('issue-card')).toHaveCount(2);
  });

  // E2E-06: SeverityBadge renders for critical
  test('E2E-06: severity badge renders for critical', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ISSUES_PAGE_1) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    const badges = page.getByTestId('severity-badge');
    await expect(badges.first()).toContainText('critical');
  });

  // E2E-07: Overdue due_at renders in red
  test('E2E-07: overdue due_at shown in red', async ({ page }) => {
    await setupAuth(page);
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        items: [ISSUE_1],
        total: 1,
        page: 1,
        page_size: 25,
        has_next: false,
      }) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);
    // ISSUE_1 has due_at in the past (2020-01-01) → should be red
    const dueCell = page.locator('.text-red-400').first();
    await expect(dueCell).toBeVisible();
  });

  // E2E-08: Workspace detail quick link navigates to issues page
  test('E2E-08: workspace detail issues quick link', async ({ page }) => {
    await setupAuth(page);

    // Mock workspace detail endpoint
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}`, (route) => {
      if (route.request().url().includes('/issues')) return route.fallback();
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(WORKSPACE_FIXTURE) });
    });
    // Mock workspace role check
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/members/*/role`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ role: 'workspace_administrator' }) });
    });
    // Mock issues endpoint for when we navigate there
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues*`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ISSUES_PAGE_1) });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}`);
    const issuesLink = page.getByTestId('issues-quick-link');
    await expect(issuesLink).toBeVisible();
    await issuesLink.click();
    await expect(page).toHaveURL(new RegExp(`/workspaces/${WORKSPACE_ID}/issues`));
  });
});
