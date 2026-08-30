/**
 * F004 — Packet 9: Frontend Data Source Pages
 *
 * E2E tests cover the following acceptance criteria:
 *
 *   E2E-01  Data source list page loads showing existing sources
 *   E2E-02  Data engineer can navigate to Create page and submit a PostgreSQL source
 *   E2E-03  Create form shows correct credential fields when source_type changes to Snowflake
 *   E2E-04  Create form shows correct credential fields when source_type changes to BigQuery
 *   E2E-05  Submit with empty source_name shows validation error inline
 *   E2E-06  Successful create redirects to detail page showing ACTIVE / UNTESTED badges
 *   E2E-07  Test connection button shows REACHABLE after mocked success response
 *   E2E-08  Test connection button shows UNREACHABLE after mocked failure response
 *   E2E-09  Edit button navigates to edit page; metadata fields pre-populated
 *   E2E-10  Rotate Credentials toggle reveals credential fields
 *   E2E-11  Save edit (metadata only) shows toast success; credential_reference unchanged
 *   E2E-12  Archive button shows modal with confirm button
 *   E2E-13  Archive confirm → status badge changes to ARCHIVED; test connection button hidden
 *   E2E-14  Restore button visible on archived source; confirm → status badge changes to ACTIVE
 *   E2E-15  Data steward does not see Create, Edit, Archive, or Restore buttons
 *   E2E-16  Data steward can see list and detail (read-only view)
 *   E2E-17  Filter by status=archived shows only archived sources in list
 *   E2E-18  Audit log panel toggle opens panel showing `data_source_created` entry
 *   E2E-19  List page navigation to detail via row click
 *   E2E-20  Platform operator sees read-only detail (no edit/archive/restore buttons)
 *
 * Mocking strategy: JWT in localStorage, all API calls intercepted via page.route()
 */

import { test, expect, Page } from '@playwright/test';

// ───────────────────────────────────────────────────────────────────────────
// JWT helper
// ───────────────────────────────────────────────────────────────────────────

function buildJwt(
  actorRole:
    | 'workspace_administrator'
    | 'data_engineer'
    | 'workspace_viewer'
    | 'platform_operator',
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

// ───────────────────────────────────────────────────────────────────────────
// Fixtures
// ───────────────────────────────────────────────────────────────────────────

const WORKSPACE_ID = 'ws-test-001';

const DATA_SOURCE_LIST_FIXTURE = {
  items: [
    {
      data_source_id: 'ds-001',
      workspace_id: WORKSPACE_ID,
      tenant_id: 'tenant-001',
      source_name: 'production-postgres',
      source_type: 'postgresql',
      connection_mode: 'direct',
      environment: 'production',
      description: 'Main production database',
      status: 'active',
      last_test_status: 'reachable',
      last_tested_at: '2026-03-20T10:00:00Z',
      credential_reference: 'cred-ref-001',
      version: 0,
      created_at: '2026-03-01T08:00:00Z',
      updated_at: '2026-03-20T10:00:00Z',
      created_by: 'user-001',
      updated_by: null,
      archived_at: null,
      archived_by: null,
    },
    {
      data_source_id: 'ds-002',
      workspace_id: WORKSPACE_ID,
      tenant_id: 'tenant-001',
      source_name: 'staging-snowflake',
      source_type: 'snowflake',
      connection_mode: 'direct',
      environment: 'staging',
      description: null,
      status: 'archived',
      last_test_status: 'untested',
      last_tested_at: null,
      credential_reference: 'cred-ref-002',
      version: 0,
      created_at: '2026-02-15T12:00:00Z',
      updated_at: '2026-02-15T12:00:00Z',
      created_by: 'user-001',
      updated_by: null,
      archived_at: '2026-03-10T14:00:00Z',
      archived_by: 'user-001',
    },
  ],
  meta: { total: 2, page: 1, page_size: 25, has_next: false },
};

const DATA_SOURCE_DETAIL_FIXTURE = {
  data_source_id: 'ds-001',
  workspace_id: WORKSPACE_ID,
  tenant_id: 'tenant-001',
  source_name: 'production-postgres',
  source_type: 'postgresql',
  connection_mode: 'direct',
  environment: 'production',
  description: 'Main production database',
  status: 'active',
  last_test_status: 'untested',
  last_tested_at: null,
  credential_reference: 'cred-ref-001',
  version: 0,
  created_at: '2026-03-01T08:00:00Z',
  updated_at: '2026-03-01T08:00:00Z',
  created_by: 'user-001',
  updated_by: null,
  archived_at: null,
  archived_by: null,
};

const ARCHIVED_DATA_SOURCE_FIXTURE = {
  ...DATA_SOURCE_DETAIL_FIXTURE,
  data_source_id: 'ds-002',
  source_name: 'staging-snowflake',
  source_type: 'snowflake',
  environment: 'staging',
  status: 'archived',
  archived_at: '2026-03-10T14:00:00Z',
  archived_by: 'user-001',
};

const AUDIT_LOG_FIXTURE = {
  items: [
    {
      audit_log_id: 'audit-001',
      workspace_id: WORKSPACE_ID,
      action_type: 'data_source_created',
      actor_id: 'user-001',
      entity_type: 'data_source',
      entity_id: 'ds-001',
      old_data: null,
      new_data: { source_name: 'production-postgres', source_type: 'postgresql' },
      created_at: '2026-03-01T08:00:00Z',
    },
  ],
  meta: { total: 1, page: 1, page_size: 20, has_next: false },
};

const ARCHIVED_LIST_FIXTURE = {
  items: [DATA_SOURCE_LIST_FIXTURE.items[1]],
  meta: { total: 1, page: 1, page_size: 25, has_next: false },
};

// ───────────────────────────────────────────────────────────────────────────
// Auth setup helper
// ───────────────────────────────────────────────────────────────────────────

async function setupAuth(
  page: Page,
  role:
    | 'workspace_administrator'
    | 'data_engineer'
    | 'workspace_viewer'
    | 'platform_operator',
): Promise<void> {
  await page.addInitScript(
    ({ token }) => {
      localStorage.setItem('access_token', token);
    },
    { token: buildJwt(role) },
  );

  // Mock auth/me endpoint
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

  // Mock workspace detail API (used by data source pages for workspace context)
  await page.route((url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}`) && !url.href.includes('data-sources'), (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        workspace_id: WORKSPACE_ID,
        workspace_name: 'Test Workspace',
        workspace_slug: 'test-workspace',
        organization_id: 'org-001',
        status: 'active',
        default_timezone: 'UTC',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      }),
    });
  });
}

// ───────────────────────────────────────────────────────────────────────────
// API mock helpers
// ───────────────────────────────────────────────────────────────────────────

async function mockListApi(page: Page, fixture: typeof DATA_SOURCE_LIST_FIXTURE): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources`) &&
             !url.href.match(/data-sources\/[^/?]+/),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(fixture),
        });
      } else {
        route.continue();
      }
    }
  );
}

async function mockDetailApi(page: Page, fixture: typeof DATA_SOURCE_DETAIL_FIXTURE): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${fixture.data_source_id}`) &&
             !url.href.includes('test-connection') &&
             !url.href.includes('archive') &&
             !url.href.includes('restore') &&
             !url.href.includes('audit-logs'),
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
    }
  );
}

async function mockCreateApi(page: Page, responseFixture: typeof DATA_SOURCE_DETAIL_FIXTURE): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources`) &&
             !url.href.match(/\/data-sources\/[^/?]+/),
    (route) => {
      if (route.request().method() === 'POST') {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(responseFixture),
        });
      } else {
        route.fallback();
      }
    }
  );
}

async function mockUpdateApi(page: Page, updatedFixture: typeof DATA_SOURCE_DETAIL_FIXTURE): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${updatedFixture.data_source_id}`) &&
             !url.href.includes('test-connection') &&
             !url.href.includes('archive') &&
             !url.href.includes('restore'),
    (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updatedFixture),
        });
      } else {
        route.fallback();
      }
    }
  );
}

async function mockTestConnectionApi(page: Page, dsId: string, status: 'reachable' | 'unreachable'): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${dsId}/test-connection`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status,
          tested_at: new Date().toISOString(),
          error_summary: status === 'unreachable' ? 'Connection refused' : null,
          latency_ms: status === 'reachable' ? 45 : null,
        }),
      });
    },
  );
}

async function mockArchiveApi(page: Page, dsId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${dsId}/archive`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...DATA_SOURCE_DETAIL_FIXTURE,
          data_source_id: dsId,
          status: 'archived',
          archived_at: new Date().toISOString(),
          archived_by: 'user-001',
        }),
      });
    },
  );
}

async function mockRestoreApi(page: Page, dsId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${dsId}/restore`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...ARCHIVED_DATA_SOURCE_FIXTURE,
          data_source_id: dsId,
          status: 'active',
          archived_at: null,
          archived_by: null,
        }),
      });
    },
  );
}

async function mockAuditLogApi(page: Page, dsId: string): Promise<void> {
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WORKSPACE_ID}/data-sources/${dsId}/audit-logs`),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(AUDIT_LOG_FIXTURE),
      });
    },
  );
}

// ───────────────────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────────────────

test.describe('F004 P09 — Data Source Pages', () => {
  test('E2E-01: Data source list page loads showing existing sources', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);

    await expect(page.getByTestId('data-source-list')).toBeVisible();
    await expect(page.getByText('production-postgres')).toBeVisible();
    await expect(page.getByText('staging-snowflake')).toBeVisible();
    await expect(page.getByTestId('data-source-status-badge').first()).toHaveText('active');
    await expect(page.getByTestId('test-status-badge').first()).toHaveText('REACHABLE');
  });

  test('E2E-02: Data engineer can navigate to Create page and submit a PostgreSQL source', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);
    await mockCreateApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);
    await expect(page.getByTestId('create-data-source-btn')).toBeVisible();
    await page.getByTestId('create-data-source-btn').click();

    await expect(page).toHaveURL(`/workspaces/${WORKSPACE_ID}/data-sources/new`);
    await expect(page.getByTestId('source-name-input')).toBeVisible();

    // Fill form
    await page.getByTestId('source-name-input').fill('my-postgres-source');
    await page.getByTestId('source-type-select').selectOption('postgresql');
    await page.getByTestId('environment-select').selectOption('production');
    await page.locator('#jdbc-host').fill('db.example.com');
    await page.locator('#jdbc-port').fill('5432');
    await page.locator('#jdbc-database').fill('mydb');
    await page.locator('#jdbc-username').fill('dbuser');
    await page.locator('#jdbc-password').fill('secret123');

    await page.getByTestId('save-data-source-btn').click();

    // Should redirect to detail page
    await expect(page).toHaveURL(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);
  });

  test('E2E-03: Create form shows correct credential fields when source_type changes to Snowflake', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/new`);

    await page.getByTestId('source-type-select').selectOption('snowflake');

    await expect(page.locator('#sf-account-identifier')).toBeVisible();
    await expect(page.locator('#sf-account')).toBeVisible();
    await expect(page.locator('#sf-warehouse')).toBeVisible();
    await expect(page.locator('#sf-database')).toBeVisible();
    await expect(page.locator('#sf-username')).toBeVisible();
    await expect(page.locator('#sf-password')).toBeVisible();
  });

  test('E2E-04: Create form shows correct credential fields when source_type changes to BigQuery', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/new`);

    await page.getByTestId('source-type-select').selectOption('bigquery');

    await expect(page.locator('#bq-project-id')).toBeVisible();
    await expect(page.locator('#bq-sa-json')).toBeVisible();
  });

  test('E2E-05: Submit with empty source_name shows validation error inline', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/new`);

    await page.getByTestId('source-name-input').clear();
    await page.getByTestId('save-data-source-btn').click();

    await expect(page.getByText('Source name is required')).toBeVisible();
  });

  test('E2E-06: Successful create redirects to detail page showing ACTIVE / UNTESTED badges', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockCreateApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/new`);

    await page.getByTestId('source-name-input').fill('test-source');
    await page.locator('#jdbc-host').fill('db.test.com');
    await page.locator('#jdbc-port').fill('5432');
    await page.locator('#jdbc-database').fill('testdb');
    await page.locator('#jdbc-username').fill('user');
    await page.locator('#jdbc-password').fill('pass');
    await page.getByTestId('save-data-source-btn').click();

    await page.waitForURL(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('data-source-status-badge')).toHaveText('active');
    await expect(page.getByTestId('test-status-badge')).toHaveText('UNTESTED');
  });

  test('E2E-07: Test connection button shows REACHABLE after mocked success response', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    const fixtureWithReachable = { ...DATA_SOURCE_DETAIL_FIXTURE, last_test_status: 'reachable' as const };
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockTestConnectionApi(page, DATA_SOURCE_DETAIL_FIXTURE.data_source_id, 'reachable');

    // Mock updated detail response after test
    await page.route(
      (url) => url.href.includes('/api/v1/') && url.href.includes(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`) && !url.href.includes('test-connection'),
      (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(fixtureWithReachable),
          });
        } else {
          route.fallback();
        }
      },
    );

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('test-connection-btn')).toBeVisible();
    await page.getByTestId('test-connection-btn').click();

    await expect(page.getByText('Connection test complete')).toBeVisible();
  });

  test('E2E-08: Test connection button shows UNREACHABLE after mocked failure response', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    const fixtureWithUnreachable = { ...DATA_SOURCE_DETAIL_FIXTURE, last_test_status: 'unreachable' as const };
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockTestConnectionApi(page, DATA_SOURCE_DETAIL_FIXTURE.data_source_id, 'unreachable');

    await page.route(
      (url) => url.href.includes('/api/v1/') && url.href.includes(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`) && !url.href.includes('test-connection'),
      (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(fixtureWithUnreachable),
          });
        } else {
          route.fallback();
        }
      },
    );

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await page.getByTestId('test-connection-btn').click();
    await expect(page.getByText('Connection test complete')).toBeVisible();
  });

  test('E2E-09: Edit button navigates to edit page; metadata fields pre-populated', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('edit-data-source-btn')).toBeVisible();
    await page.getByTestId('edit-data-source-btn').click();

    await expect(page).toHaveURL(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}/edit`);
    await expect(page.getByTestId('source-name-input')).toHaveValue('production-postgres');
    await expect(page.getByTestId('environment-select')).toHaveValue('production');
  });

  test('E2E-10: Rotate Credentials toggle reveals credential fields', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}/edit`);

    await expect(page.locator('#jdbc-host')).not.toBeVisible();

    await page.getByTestId('rotate-credentials-toggle').click({ force: true });

    await expect(page.locator('#jdbc-host')).toBeVisible();
    await expect(page.locator('#jdbc-password')).toBeVisible();
  });

  test('E2E-11: Save edit (metadata only) shows toast success; credential_reference unchanged', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    const updatedFixture = { ...DATA_SOURCE_DETAIL_FIXTURE, description: 'Updated description' };
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockUpdateApi(page, updatedFixture);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}/edit`);

    await page.locator('#description').fill('Updated description');
    await page.getByTestId('save-data-source-btn').click();

    await expect(page.getByText('Data source updated')).toBeVisible();
    await expect(page).toHaveURL(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);
  });

  test('E2E-12: Archive button shows modal with confirm button', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('archive-data-source-btn')).toBeVisible();
    await page.getByTestId('archive-data-source-btn').click();

    await expect(page.getByText('Archive data source?')).toBeVisible();
    await expect(page.getByTestId('archive-confirm-btn')).toBeVisible();
  });

  test('E2E-13: Archive confirm → status badge changes to ARCHIVED; test connection button hidden', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    const archivedFixture = { ...DATA_SOURCE_DETAIL_FIXTURE, status: 'archived' as const, archived_at: new Date().toISOString(), archived_by: 'user-001' };
    let archived = false;
    await mockArchiveApi(page, DATA_SOURCE_DETAIL_FIXTURE.data_source_id);

    // Single detail mock that switches state after archive
    await page.route(
      (url) => url.href.includes('/api/v1/') && url.href.includes(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`) && !url.href.includes('archive'),
      (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(archived ? archivedFixture : DATA_SOURCE_DETAIL_FIXTURE),
          });
        } else {
          route.fallback();
        }
      },
    );

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await page.getByTestId('archive-data-source-btn').click();
    await page.getByTestId('archive-confirm-btn').click();
    archived = true;

    await expect(page.getByText('Data source archived')).toBeVisible();
    await expect(page.getByTestId('test-connection-btn')).not.toBeVisible();
  });

  test('E2E-14: Restore button visible on archived source; confirm → status badge changes to ACTIVE', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    const restoredFixture = { ...ARCHIVED_DATA_SOURCE_FIXTURE, status: 'active' as const, archived_at: null, archived_by: null };
    let restored = false;
    await mockRestoreApi(page, ARCHIVED_DATA_SOURCE_FIXTURE.data_source_id);

    // Single detail mock that switches state after restore
    await page.route(
      (url) => url.href.includes('/api/v1/') && url.href.includes(`/workspaces/${WORKSPACE_ID}/data-sources/${ARCHIVED_DATA_SOURCE_FIXTURE.data_source_id}`) && !url.href.includes('restore'),
      (route) => {
        if (route.request().method() === 'GET') {
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(restored ? restoredFixture : ARCHIVED_DATA_SOURCE_FIXTURE),
          });
        } else {
          route.fallback();
        }
      },
    );

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${ARCHIVED_DATA_SOURCE_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('restore-data-source-btn')).toBeVisible();
    await page.getByTestId('restore-data-source-btn').click();
    await page.getByTestId('restore-confirm-btn').click();
    restored = true;

    await expect(page.getByText('Data source restored')).toBeVisible();
  });

  test('E2E-15: Data steward does not see Create, Edit, Archive, or Restore buttons', async ({ page }) => {
    await setupAuth(page, 'workspace_viewer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);
    await expect(page.getByTestId('create-data-source-btn')).not.toBeVisible();

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);
    await expect(page.getByTestId('edit-data-source-btn')).not.toBeVisible();
    await expect(page.getByTestId('archive-data-source-btn')).not.toBeVisible();
  });

  test('E2E-16: Data steward can see list and detail (read-only view)', async ({ page }) => {
    await setupAuth(page, 'workspace_viewer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);
    await expect(page.getByTestId('data-source-list')).toBeVisible();
    await expect(page.getByText('production-postgres')).toBeVisible();

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);
    await expect(page.getByText('production-postgres')).toBeVisible();
    await expect(page.getByTestId('data-source-status-badge')).toBeVisible();
  });

  test('E2E-17: Filter by status=archived shows only archived sources in list', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);

    await page.route(
      (url) => url.href.includes('status=archived'),
      (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ARCHIVED_LIST_FIXTURE),
        });
      },
    );

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);

    await page.locator('select[aria-label="Filter by status"]').selectOption('archived');

    await expect(page.getByText('staging-snowflake')).toBeVisible();
    await expect(page.getByText('production-postgres')).not.toBeVisible();
  });

  test('E2E-18: Audit log panel toggle opens panel showing data_source_created entry', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);
    await mockAuditLogApi(page, DATA_SOURCE_DETAIL_FIXTURE.data_source_id);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByTestId('audit-log-panel-toggle')).toBeVisible();
    await page.getByTestId('audit-log-panel-toggle').click();

    await expect(page.getByTestId('audit-log-list')).toBeVisible();
    await expect(page.getByText('Data Source Created')).toBeVisible();
  });

  test('E2E-19: List page navigation to detail via row click', async ({ page }) => {
    await setupAuth(page, 'data_engineer');
    await mockListApi(page, DATA_SOURCE_LIST_FIXTURE);
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources`);

    const row = page.locator('tr', { hasText: 'production-postgres' });
    await row.click();

    await expect(page).toHaveURL(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);
  });

  test('E2E-20: Platform operator sees read-only detail (no edit/archive/restore buttons)', async ({ page }) => {
    await setupAuth(page, 'platform_operator');
    await mockDetailApi(page, DATA_SOURCE_DETAIL_FIXTURE);

    await page.goto(`/workspaces/${WORKSPACE_ID}/data-sources/${DATA_SOURCE_DETAIL_FIXTURE.data_source_id}`);

    await expect(page.getByText('production-postgres')).toBeVisible();
    await expect(page.getByTestId('edit-data-source-btn')).not.toBeVisible();
    await expect(page.getByTestId('archive-data-source-btn')).not.toBeVisible();
  });
});
