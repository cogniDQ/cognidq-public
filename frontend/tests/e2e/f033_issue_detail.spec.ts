/**
 * F033 — Packet 3: Frontend Issue Detail Page
 *
 * E2E tests cover the primary user flows:
 *
 *   E2E-01  Detail page loads with all context cards
 *   E2E-02  Loading skeleton displayed while fetching
 *   E2E-03  404 state for missing issue
 *   E2E-04  Issue list row navigates to detail
 *   E2E-05  Rule link navigation
 *   E2E-06  Dataset link navigation
 *   E2E-07  Overdue indicator
 *   E2E-08  Null contexts handled gracefully
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

const WORKSPACE_ID = 'ws-test-f033';
const ISSUE_ID = 'iss-f033-001';

const ENRICHED_ISSUE = {
  id: ISSUE_ID,
  workspace_id: WORKSPACE_ID,
  tenant_id: 'tenant-001',
  flow_execution_id: 'exec-001',
  flow_node_result_id: 'nr-001',
  rule_id: 'rule-001',
  dataset_id: 'ds-001',
  assignee_id: 'user-001',
  issue_type: 'threshold_breach',
  severity: 'critical',
  status: 'open',
  title: '[CRITICAL] Completeness check failed',
  impact_summary: '50 of 100 rows failed (50.0% pass rate)',
  failure_count: 50,
  rows_scanned: 100,
  pass_rate: 50.0,
  due_at: '2020-01-01T00:00:00Z',  // overdue
  opened_at: new Date(Date.now() - 3_600_000).toISOString(),
  resolved_at: null,
  closed_at: null,
  updated_at: new Date().toISOString(),
  created_at: new Date(Date.now() - 7_200_000).toISOString(),
  rule: {
    id: 'rule-001',
    name: 'Completeness Check',
    category: 'completeness',
    severity: 'critical',
    status: 'active',
    target_table: 'orders',
    target_columns: ['email'],
  },
  dataset: {
    dataset_id: 'ds-001',
    dataset_name: 'Orders Dataset',
    business_domain: 'finance',
    criticality: 'high',
    status: 'active',
  },
  assignee: {
    id: 'user-001',
    display_name: 'Jane Doe',
    email: 'jane@example.com',
  },
  flow_execution: {
    id: 'exec-001',
    flow_name: 'Daily DQ Flow',
    status: 'completed',
    started_at: new Date(Date.now() - 3_600_000).toISOString(),
    completed_at: new Date().toISOString(),
    nodes_total: 5,
    nodes_passed: 4,
    nodes_failed: 1,
  },
  node_result: {
    id: 'nr-001',
    node_id: 'check_email',
    node_type: 'check',
    status: 'failed',
    rows_scanned: 100,
    rows_passed: 50,
    rows_failed: 50,
    pass_rate: 50.0,
  },
};

const ISSUE_LIST_ITEM = {
  id: ISSUE_ID,
  workspace_id: WORKSPACE_ID,
  issue_type: 'threshold_breach',
  severity: 'critical',
  status: 'open',
  title: '[CRITICAL] Completeness check failed',
  impact_summary: '50 of 100 rows failed',
  failure_count: 50,
  due_at: '2020-01-01T00:00:00Z',
  opened_at: new Date(Date.now() - 3_600_000).toISOString(),
};

// ────────────────────────────────────────────────────────────────────────────
// Setup helper
// ────────────────────────────────────────────────────────────────────────────

async function setupAuth(page: Page) {
  const jwt = buildJwt('data_engineer');
  await page.addInitScript((token: string) => {
    window.localStorage.setItem('access_token', token);
  }, jwt);
}

async function mockDetailApi(page: Page, response: object | null, statusCode = 200) {
  await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`, (route) =>
    route.fulfill({
      status: statusCode,
      contentType: 'application/json',
      body: JSON.stringify(response ?? { detail: 'Issue not found.' }),
    }),
  );
}

async function mockListApi(page: Page) {
  await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues`, (route) => {
    const url = new URL(route.request().url());
    // Only intercept list (no issue_id in path)
    if (url.pathname.endsWith('/issues') || url.pathname.endsWith('/issues/')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [ISSUE_LIST_ITEM],
          total: 1,
          page: 1,
          page_size: 25,
          has_next: false,
        }),
      });
    }
    return route.continue();
  });
}

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F033 Issue Detail Page', () => {
  test('E2E-01: Detail page loads with all context cards', async ({ page }) => {
    await setupAuth(page);
    await mockDetailApi(page, ENRICHED_ISSUE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    await expect(page.getByTestId('issue-detail')).toBeVisible();
    await expect(page.getByTestId('severity-badge')).toBeVisible();
    await expect(page.getByTestId('status-badge')).toBeVisible();
    await expect(page.getByTestId('rule-card')).toBeVisible();
    await expect(page.getByTestId('dataset-card')).toBeVisible();
    await expect(page.getByTestId('execution-card')).toBeVisible();
    await expect(page.getByTestId('node-result-card')).toBeVisible();
    await expect(page.getByTestId('assignee-card')).toBeVisible();

    // Verify content
    await expect(page.getByText('Completeness Check')).toBeVisible();
    await expect(page.getByText('Orders Dataset')).toBeVisible();
    await expect(page.getByText('Jane Doe')).toBeVisible();
    await expect(page.getByText('Daily DQ Flow')).toBeVisible();
    await expect(page.getByText('check_email')).toBeVisible();
  });

  test('E2E-02: Loading skeleton displayed while fetching', async ({ page }) => {
    await setupAuth(page);

    // Delay the API response to see skeleton
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`, async (route) => {
      await new Promise((r) => setTimeout(r, 2000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ENRICHED_ISSUE),
      });
    });

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);
    await expect(page.getByTestId('issue-detail-loading')).toBeVisible();
  });

  test('E2E-03: 404 state for missing issue', async ({ page }) => {
    await setupAuth(page);
    await mockDetailApi(page, null, 404);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    await expect(page.getByTestId('issue-detail-error')).toBeVisible();
    await expect(page.getByText('Issue not found.')).toBeVisible();
  });

  test('E2E-04: Issue list row navigates to detail', async ({ page }) => {
    await setupAuth(page);
    await mockListApi(page);
    await mockDetailApi(page, ENRICHED_ISSUE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues`);

    // Click the title link in the issue list
    const titleLink = page.getByTestId('issue-title-link').first();
    await expect(titleLink).toBeVisible();
    await titleLink.click();

    // Should navigate to detail page
    await expect(page).toHaveURL(new RegExp(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`));
    await expect(page.getByTestId('issue-detail')).toBeVisible();
  });

  test('E2E-05: Rule link navigation', async ({ page }) => {
    await setupAuth(page);
    await mockDetailApi(page, ENRICHED_ISSUE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    const ruleLink = page.getByTestId('rule-link');
    await expect(ruleLink).toBeVisible();
    await expect(ruleLink).toHaveText('Completeness Check');
    const href = await ruleLink.getAttribute('href');
    expect(href).toContain('/rules');
  });

  test('E2E-06: Dataset link navigation', async ({ page }) => {
    await setupAuth(page);
    await mockDetailApi(page, ENRICHED_ISSUE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    const datasetLink = page.getByTestId('dataset-link');
    await expect(datasetLink).toBeVisible();
    await expect(datasetLink).toHaveText('Orders Dataset');
    const href = await datasetLink.getAttribute('href');
    expect(href).toContain('/datasets');
  });

  test('E2E-07: Overdue indicator', async ({ page }) => {
    await setupAuth(page);
    await mockDetailApi(page, ENRICHED_ISSUE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    await expect(page.getByTestId('overdue-indicator')).toBeVisible();
    await expect(page.getByTestId('overdue-indicator')).toHaveText('OVERDUE');
  });

  test('E2E-08: Null contexts handled gracefully', async ({ page }) => {
    await setupAuth(page);

    const issueWithNulls = {
      ...ENRICHED_ISSUE,
      rule: null,
      dataset: null,
      assignee: null,
      flow_execution: null,
      node_result: null,
    };
    await mockDetailApi(page, issueWithNulls);

    await page.goto(`/workspaces/${WORKSPACE_ID}/issues/${ISSUE_ID}`);

    await expect(page.getByTestId('issue-detail')).toBeVisible();
    await expect(page.getByTestId('rule-card')).toContainText('Rule not available');
    await expect(page.getByTestId('dataset-card')).toContainText('Dataset not available');
    await expect(page.getByTestId('assignee-card')).toContainText('Unassigned');
    await expect(page.getByTestId('execution-card')).toContainText('Execution not available');
    await expect(page.getByTestId('node-result-card')).toContainText('Node result not available');
  });
});
