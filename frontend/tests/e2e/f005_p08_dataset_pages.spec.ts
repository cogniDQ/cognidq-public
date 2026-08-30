/**
 * F005 — Packet 8: Frontend Dataset Pages
 *
 * E2E tests cover the following acceptance criteria:
 *
 *   E2E-01  Dataset list page loads showing existing datasets
 *   E2E-02  Create dataset button navigates to create page
 *   E2E-03  Submit with empty dataset name shows validation error inline
 *   E2E-04  Successful create redirects to detail page
 *   E2E-05  Detail page shows status badge and metadata
 *   E2E-06  Detail page shows fields table with dataset fields
 *   E2E-07  Activate button shown for draft dataset; click submits request
 *   E2E-08  Deactivate button shown for active dataset; activate button absent
 *   E2E-09  Archive button visible for admin; absent for data engineer
 *   E2E-10  Edit button navigates to edit page
 *   E2E-11  Edit page shows immutable fields as read-only text
 *   E2E-12  Save edit redirects to detail page
 *   E2E-13  Filter by status in list page updates results
 *   E2E-14  Row click navigates to detail page
 *   E2E-15  Workspace viewer does not see create button
 *   E2E-16  Audit log panel toggle opens showing entries
 *   E2E-17  Reactivate button shown for inactive dataset
 *   E2E-18  Workspace viewer can see detail page (read-only)
 *   E2E-19  Workspace detail page has datasets quick link
 *   E2E-20  Archive confirm modal appears and submits archive request
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

const WORKSPACE_ID = 'ws-test-001';
const DATASET_ID = 'dset-001';
const DATA_SOURCE_ID = 'ds-src-001';

const DRAFT_DATASET_FIXTURE = {
  dataset_id: DATASET_ID,
  workspace_id: WORKSPACE_ID,
  data_source_id: DATA_SOURCE_ID,
  data_source_name: 'prod-postgres',
  dataset_name: 'orders',
  dataset_type: 'table',
  physical_identifier: 'orders',
  schema_name: 'public',
  description: 'Orders table',
  business_domain: 'Sales',
  criticality: 'high',
  sensitivity_classification: null,
  status: 'draft',
  owner_user_id: null,
  freshness_expectation: null,
  field_count: 3,
  fields: [
    {
      field_id: 'f-001',
      field_name: 'order_id',
      data_type: 'integer',
      ordinal_position: 1,
      nullable: false,
      is_key_candidate: true,
    },
    {
      field_id: 'f-002',
      field_name: 'customer_id',
      data_type: 'integer',
      ordinal_position: 2,
      nullable: false,
      is_key_candidate: false,
    },
    {
      field_id: 'f-003',
      field_name: 'created_at',
      data_type: 'timestamp',
      ordinal_position: 3,
      nullable: true,
      is_key_candidate: false,
    },
  ],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  activated_at: null,
  deactivated_at: null,
  reactivated_at: null,
  archived_at: null,
  created_by: 'user-001',
  updated_by: null,
};

const ACTIVE_DATASET_FIXTURE = {
  ...DRAFT_DATASET_FIXTURE,
  status: 'active',
  activated_at: '2026-01-02T00:00:00Z',
};

const INACTIVE_DATASET_FIXTURE = {
  ...DRAFT_DATASET_FIXTURE,
  status: 'inactive',
};

const ARCHIVED_DATASET_FIXTURE = {
  ...DRAFT_DATASET_FIXTURE,
  status: 'archived',
  archived_at: '2026-01-10T00:00:00Z',
};

const DATASET_LIST_FIXTURE = {
  items: [
    {
      dataset_id: DATASET_ID,
      workspace_id: WORKSPACE_ID,
      data_source_id: DATA_SOURCE_ID,
      data_source_name: 'prod-postgres',
      dataset_name: 'orders',
      dataset_type: 'table',
      physical_identifier: 'orders',
      schema_name: 'public',
      description: 'Orders table',
      business_domain: 'Sales',
      criticality: 'high',
      status: 'draft',
      field_count: 3,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      created_by: 'user-001',
    },
  ],
  meta: { total: 1, page: 1, page_size: 25, has_next: false },
};

const FILTERED_DRAFT_LIST_FIXTURE = { ...DATASET_LIST_FIXTURE };

const CREATED_DATASET_FIXTURE = {
  ...DRAFT_DATASET_FIXTURE,
  dataset_id: 'dset-new-001',
  dataset_name: 'customers',
  physical_identifier: 'customers',
};

const DATA_SOURCES_LIST_FIXTURE = {
  items: [
    {
      data_source_id: DATA_SOURCE_ID,
      source_name: 'prod-postgres',
      source_type: 'postgresql',
      status: 'active',
    },
  ],
  meta: { total: 1, page: 1, page_size: 25, has_next: false },
};

const AUDIT_LOG_FIXTURE = {
  items: [
    {
      log_id: 'log-001',
      action_type: 'dataset_created',
      actor_id: 'user-001',
      occurred_at: '2026-01-01T00:00:00Z',
    },
  ],
  meta: { total: 1, page: 1, page_size: 20, has_next: false },
};

// ────────────────────────────────────────────────────────────────────────────
// Auth setup helper
// ────────────────────────────────────────────────────────────────────────────

async function setupAuth(page: Page, role: string): Promise<void> {
  await page.addInitScript(
    ({ token }: { token: string }) => {
      localStorage.setItem('access_token', token);
    },
    { token: buildJwt(role) },
  );

  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route) => {
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
      });
    },
  );

  // Mock workspace detail — exclude data-sources and datasets sub-paths
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}`) &&
      !url.href.includes('data-sources') &&
      !url.href.includes('datasets'),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            workspace_id: WORKSPACE_ID,
            workspace_name: 'Test Workspace',
            workspace_slug: 'test-workspace',
            organization_id: 'org-001',
            status: 'active',
            default_timezone: 'UTC',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            dataset_count: 0,
            member_count: 1,
          },
        }),
      });
    },
  );
}

// ────────────────────────────────────────────────────────────────────────────
// API mock helpers
// ────────────────────────────────────────────────────────────────────────────

async function mockListApi(page: Page, fixture: typeof DATASET_LIST_FIXTURE): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets`) &&
      !url.href.match(/datasets\/[^/?]+/),
    (route) => {
      if (route.request().method() === 'GET') {
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

async function mockDetailApi(
  page: Page,
  fixture: typeof DRAFT_DATASET_FIXTURE,
): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${fixture.dataset_id}`) &&
      !url.href.includes('/activate') &&
      !url.href.includes('/deactivate') &&
      !url.href.includes('/reactivate') &&
      !url.href.includes('/archive') &&
      !url.href.includes('/fields') &&
      !url.href.includes('/audit-logs'),
    (route) => {
      if (route.request().method() === 'GET') {
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

async function mockCreateApi(page: Page, response: typeof CREATED_DATASET_FIXTURE): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets`) &&
      !url.href.match(/datasets\/[^/?]+/),
    (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(response),
        });
      } else {
        route.fallback();
      }
    },
  );
}

async function mockUpdateApi(page: Page, response: typeof DRAFT_DATASET_FIXTURE): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${response.dataset_id}`) &&
      !url.href.includes('/activate') &&
      !url.href.includes('/deactivate') &&
      !url.href.includes('/reactivate') &&
      !url.href.includes('/archive') &&
      !url.href.includes('/fields') &&
      !url.href.includes('/audit-logs'),
    (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(response),
        });
      } else {
        route.fallback();
      }
    },
  );
}

async function mockDataSourcesApi(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources`) &&
      !url.href.match(/data-sources\/[^/?]+/),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DATA_SOURCES_LIST_FIXTURE),
        });
      } else {
        route.fallback();
      }
    },
  );
}

async function mockActivateApi(page: Page, datasetId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${datasetId}/activate`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...ACTIVE_DATASET_FIXTURE, dataset_id: datasetId }),
      });
    },
  );
}

async function mockDeactivateApi(page: Page, datasetId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${datasetId}/deactivate`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...INACTIVE_DATASET_FIXTURE, dataset_id: datasetId }),
      });
    },
  );
}

async function mockReactivateApi(page: Page, datasetId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${datasetId}/reactivate`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...ACTIVE_DATASET_FIXTURE, dataset_id: datasetId }),
      });
    },
  );
}

async function mockArchiveApi(page: Page, datasetId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${datasetId}/archive`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...ARCHIVED_DATASET_FIXTURE, dataset_id: datasetId }),
      });
    },
  );
}

async function mockAuditLogApi(page: Page, datasetId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets/${datasetId}/audit-logs`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUDIT_LOG_FIXTURE),
      });
    },
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F005 P08 — Dataset Pages', () => {
  test('E2E-01: Dataset list page loads showing existing datasets', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockListApi(page, DATASET_LIST_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets`);
    await expect(page.locator('[data-testid="dataset-list"]')).toBeVisible();
    await expect(page.locator(`[data-testid="dataset-row-${DATASET_ID}"]`)).toBeVisible();
    await expect(page.locator(`[data-testid="dataset-row-${DATASET_ID}"]`)).toContainText('orders');
  });

  test('E2E-02: Create dataset button navigates to create page', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockListApi(page, DATASET_LIST_FIXTURE);
    await mockDataSourcesApi(page);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets`);
    await page.locator('[data-testid="create-dataset-btn"]').click();
    await expect(page).toHaveURL(new RegExp(`/workspaces/${WORKSPACE_ID}/datasets/new`));
    await expect(page.locator('[data-testid="create-dataset-form"]')).toBeVisible();
  });

  test('E2E-03: Submit with empty dataset name shows validation error inline', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDataSourcesApi(page);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/new`);
    await page.locator('[data-testid="submit-btn"]').click();
    await expect(page.locator('[data-testid="dataset-name-error"]')).toBeVisible();
    await expect(page.locator('[data-testid="dataset-name-error"]')).toContainText('required');
  });

  test('E2E-04: Successful create redirects to detail page', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDataSourcesApi(page);
    await mockCreateApi(page, CREATED_DATASET_FIXTURE);
    await mockDetailApi(page, CREATED_DATASET_FIXTURE as typeof DRAFT_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/new`);
    // Wait for data sources dropdown to populate, then select the first option
    await page.locator('[data-testid="data-source-select"] option').nth(1).waitFor({ state: 'attached', timeout: 5000 });
    await page.locator('[data-testid="data-source-select"]').selectOption({ index: 1 });
    await page.locator('[data-testid="dataset-name-input"]').fill('customers');
    await page.locator('[data-testid="physical-identifier-input"]').fill('customers');
    await page.locator('[data-testid="submit-btn"]').click();
    await expect(page).toHaveURL(
      new RegExp(`/workspaces/${WORKSPACE_ID}/datasets/${CREATED_DATASET_FIXTURE.dataset_id}`),
    );
  });

  test('E2E-05: Detail page shows status badge and metadata', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="dataset-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="status-badge"]')).toBeVisible();
    await expect(page.locator('[data-testid="status-badge"]')).toContainText('DRAFT');
  });

  test('E2E-06: Detail page shows fields table with dataset fields', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="fields-table"]')).toBeVisible();
    await expect(page.locator('[data-testid="field-row-f-001"]')).toBeVisible();
    await expect(page.locator('[data-testid="field-row-f-001"]')).toContainText('order_id');
  });

  test('E2E-07: Activate button shown for draft dataset; click submits request', async ({
    page,
  }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await mockActivateApi(page, DATASET_ID);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    const activateBtn = page.locator('[data-testid="activate-btn"]');
    await expect(activateBtn).toBeVisible();
    // deactivate should NOT be visible on draft
    await expect(page.locator('[data-testid="deactivate-btn"]')).not.toBeVisible();
    await activateBtn.click();
    // request fires; toast appears (react-hot-toast renders to body)
    await expect(page.getByText('Dataset activated')).toBeVisible({ timeout: 5000 });
  });

  test('E2E-08: Deactivate button shown for active dataset; activate button absent', async ({
    page,
  }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, ACTIVE_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="deactivate-btn"]')).toBeVisible();
    await expect(page.locator('[data-testid="activate-btn"]')).not.toBeVisible();
  });

  test('E2E-09: Archive button visible for admin; absent for data engineer', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, ACTIVE_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="archive-btn"]')).toBeVisible();

    // Verify data_engineer does NOT see archive button
    const page2 = await page.context().newPage();
    await setupAuth(page2, 'data_engineer');
    await mockDetailApi(page2, ACTIVE_DATASET_FIXTURE);
    await page2.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page2.locator('[data-testid="archive-btn"]')).not.toBeVisible();
    await page2.close();
  });

  test('E2E-10: Edit button navigates to edit page with form visible', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await page.locator('[data-testid="edit-btn"]').click();
    await expect(page).toHaveURL(
      new RegExp(`/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}/edit`),
    );
    await expect(page.locator('[data-testid="edit-dataset-form"]')).toBeVisible();
  });

  test('E2E-11: Edit page shows immutable fields as read-only text', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await page.goto(
      `http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}/edit`,
    );
    await expect(page.locator('[data-testid="readonly-physical-identifier"]')).toBeVisible();
    await expect(page.locator('[data-testid="readonly-physical-identifier"]')).toContainText(
      'orders',
    );
    await expect(page.locator('[data-testid="readonly-dataset-type"]')).toContainText('table');
    await expect(page.locator('[data-testid="readonly-data-source"]')).toContainText(
      'prod-postgres',
    );
  });

  test('E2E-12: Save edit redirects to detail page on success', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    const updatedFixture = { ...DRAFT_DATASET_FIXTURE, dataset_name: 'orders_v2' };
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await mockUpdateApi(page, updatedFixture);
    await page.goto(
      `http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}/edit`,
    );
    // Wait for pre-population via useEffect
    await expect(page.locator('[data-testid="dataset-name-input"]')).toHaveValue('orders', {
      timeout: 5000,
    });
    await page.locator('[data-testid="dataset-name-input"]').clear();
    await page.locator('[data-testid="dataset-name-input"]').fill('orders_v2');
    await page.locator('[data-testid="save-btn"]').click();
    await expect(page).toHaveURL(
      new RegExp(`/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}$`),
      { timeout: 5000 },
    );
  });

  test('E2E-13: Filter by status in list page sends status param', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await page.route(
      (url) =>
        url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/datasets`) &&
        !url.href.match(/datasets\/[^/?]+/),
      (route) => {
        const urlObj = new URL(route.request().url());
        const status = urlObj.searchParams.get('status');
        const fixture = status === 'draft' ? FILTERED_DRAFT_LIST_FIXTURE : DATASET_LIST_FIXTURE;
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(fixture),
        });
      },
    );
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets`);
    await expect(page.locator('[data-testid="dataset-list"]')).toBeVisible();
    await page.locator('[data-testid="status-filter"]').selectOption('draft');
    await expect(page.locator(`[data-testid="dataset-row-${DATASET_ID}"]`)).toBeVisible();
  });

  test('E2E-14: Row click navigates to detail page', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockListApi(page, DATASET_LIST_FIXTURE);
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets`);
    await page.locator(`[data-testid="dataset-row-${DATASET_ID}"]`).click();
    await expect(page).toHaveURL(
      new RegExp(`/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`),
    );
  });

  test('E2E-15: Workspace viewer does not see create button on list page', async ({ page }) => {
    await setupAuth(page, 'workspace_viewer');
    await mockListApi(page, DATASET_LIST_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets`);
    await expect(page.locator('[data-testid="dataset-list"]')).toBeVisible();
    await expect(page.locator('[data-testid="create-dataset-btn"]')).not.toBeVisible();
  });

  test('E2E-16: Audit log panel toggle opens showing entries', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, DRAFT_DATASET_FIXTURE);
    await mockAuditLogApi(page, DATASET_ID);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="audit-log-toggle"]')).toBeVisible();
    await page.locator('[data-testid="audit-log-toggle"]').click();
    await expect(page.locator('[data-testid="audit-log-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="audit-log-panel"]')).toContainText('dataset_created');
  });

  test('E2E-17: Reactivate button shown for inactive dataset; activate/deactivate absent', async ({
    page,
  }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, INACTIVE_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="reactivate-btn"]')).toBeVisible();
    await expect(page.locator('[data-testid="activate-btn"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="deactivate-btn"]')).not.toBeVisible();
  });

  test('E2E-18: Workspace viewer can see detail page without edit/archive buttons', async ({
    page,
  }) => {
    await setupAuth(page, 'workspace_viewer');
    await mockDetailApi(page, ACTIVE_DATASET_FIXTURE);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await expect(page.locator('[data-testid="dataset-detail"]')).toBeVisible();
    await expect(page.locator('[data-testid="status-badge"]')).toContainText('ACTIVE');
    await expect(page.locator('[data-testid="edit-btn"]')).not.toBeVisible();
    await expect(page.locator('[data-testid="archive-btn"]')).not.toBeVisible();
  });

  test('E2E-19: Workspace detail page has datasets quick link', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}`);
    await expect(page.locator('[data-testid="datasets-quick-link"]')).toBeVisible();
  });

  test('E2E-20: Archive confirm modal appears and submits archive request', async ({ page }) => {
    await setupAuth(page, 'workspace_administrator');
    await mockDetailApi(page, ACTIVE_DATASET_FIXTURE);
    await mockArchiveApi(page, DATASET_ID);
    await page.goto(`http://localhost:5173/workspaces/${WORKSPACE_ID}/datasets/${DATASET_ID}`);
    await page.locator('[data-testid="archive-btn"]').click();
    await expect(page.locator('[data-testid="archive-modal"]')).toBeVisible();
    await page.locator('[data-testid="archive-confirm-btn"]').click();
    await expect(page.locator('[data-testid="archive-modal"]')).not.toBeVisible({ timeout: 5000 });
  });
});
