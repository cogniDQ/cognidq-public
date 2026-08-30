/**
 * F001 – Packet 10: Routing Foundation and Tenant List Page
 *
 * E2E tests verify:
 *   AC-10.1  Unauthenticated visitors are redirected to /login
 *   AC-10.2  platform_viewer can reach /admin/tenants and sees the list
 *   AC-10.3  platform_viewer cannot see "Create Tenant" button
 *   AC-10.4  platform_admin sees "Create Tenant" CTA
 *   AC-10.5  Filter bar allows filtering by status; URL params update
 *   AC-10.6  Table headers for Created/Updated are sortable (toggle asc/desc)
 *   AC-10.7  Empty state is shown when filters return no results
 *
 * ── Mocking strategy ──────────────────────────────────────────────────────
 * - Auth is faked by injecting a real-looking JWT into localStorage before
 *   navigation (no backend required).
 * - API calls to GET /api/v1/tenants are intercepted via page.route() and
 *   served with fixture data so no backend is needed.
 */

import { test, expect, Page, Route } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a minimal JWT with the given actor_role. The signature is bogus —
 * the frontend only client-decodes the payload, never verifies the JWT.
 */
function buildJwt(actorRole: 'platform_admin' | 'platform_viewer'): string {
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

const TENANT_FIXTURE = {
  data: [
    {
      tenant_id: 'tid-001',
      tenant_name: 'Acme Corp',
      tenant_slug: 'acme-corp',
      status: 'active',
      region: 'eu-west',
      plan: 'growth',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-03-20T08:30:00Z',
    },
    {
      tenant_id: 'tid-002',
      tenant_name: 'Beta Ltd',
      tenant_slug: 'beta-ltd',
      status: 'draft',
      region: 'us-east',
      plan: 'starter',
      created_at: '2024-02-01T12:00:00Z',
      updated_at: '2024-03-19T14:00:00Z',
    },
  ],
  meta: { total: 2, page: 1, page_size: 20, has_next: false },
};

const EMPTY_FIXTURE = {
  data: [],
  meta: { total: 0, page: 1, page_size: 20, has_next: false },
};

async function setupAuth(page: Page, role: 'platform_admin' | 'platform_viewer') {
  // Set localStorage before page scripts run
  await page.addInitScript(
    ({ token }) => {
      localStorage.setItem('access_token', token);
    },
    { token: buildJwt(role) },
  );
}

async function mockTenantsApi(page: Page, fixture: typeof TENANT_FIXTURE | typeof EMPTY_FIXTURE) {
  await page.route('**/api/v1/tenants**', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fixture),
    });
  });
}

// ---------------------------------------------------------------------------
// AC-10.1  Unauthenticated redirect
// ---------------------------------------------------------------------------

test('AC-10.1: unauthenticated user is redirected to /login when visiting /admin/tenants', async ({
  page,
}) => {
  // No auth setup — localStorage is empty
  await page.route('**/api/v1/tenants**', (route) =>
    route.fulfill({ status: 401, body: '{}' }),
  );
  await page.goto('/admin/tenants');
  await expect(page).toHaveURL(/\/login/);
});

// ---------------------------------------------------------------------------
// AC-10.2  platform_viewer can see tenant list
// ---------------------------------------------------------------------------

test('AC-10.2: platform_viewer reaches /admin/tenants and sees tenant table', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockTenantsApi(page, TENANT_FIXTURE);

  await page.goto('/admin/tenants');

  await expect(page.getByTestId('tenant-list-page')).toBeVisible();
  await expect(page.getByTestId('tenant-table')).toBeVisible();

  // Both fixture tenants should appear
  await expect(page.getByText('Acme Corp')).toBeVisible();
  await expect(page.getByText('Beta Ltd')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.3  platform_viewer does NOT see Create Tenant button
// ---------------------------------------------------------------------------

test('AC-10.3: platform_viewer does not see Create Tenant button', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockTenantsApi(page, TENANT_FIXTURE);

  await page.goto('/admin/tenants');
  await expect(page.getByTestId('tenant-list-page')).toBeVisible();

  await expect(page.getByTestId('create-tenant-btn')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-10.4  platform_admin sees Create Tenant CTA
// ---------------------------------------------------------------------------

test('AC-10.4: platform_admin sees Create Tenant button', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantsApi(page, TENANT_FIXTURE);

  await page.goto('/admin/tenants');

  await expect(page.getByTestId('create-tenant-btn')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.5  Filter bar updates URL params
// ---------------------------------------------------------------------------

test('AC-10.5: selecting a status filter updates URL and re-fetches', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockTenantsApi(page, TENANT_FIXTURE);

  await page.goto('/admin/tenants');
  await expect(page.getByTestId('tenant-list-page')).toBeVisible();

  // Intercept new request after filter change
  const requestPromise = page.waitForRequest((req) =>
    req.url().includes('/api/v1/tenants') && req.url().includes('status=active'),
  );

  await page.getByTestId('filter-status').selectOption('active');

  // URL should contain status=active
  await expect(page).toHaveURL(/status=active/);
  // Outgoing request should have status filter
  await requestPromise;
});

// ---------------------------------------------------------------------------
// AC-10.6  Sortable column headers toggle asc/desc
// ---------------------------------------------------------------------------

test('AC-10.6: clicking Created column sorts ascending then descending', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockTenantsApi(page, TENANT_FIXTURE);

  await page.goto('/admin/tenants');
  await expect(page.getByTestId('tenant-list-page')).toBeVisible();

  // First click — sort created_at desc (default switches to asc when field != active)
  await page.getByTestId('sort-created_at').click();
  await expect(page).toHaveURL(/sort_by=created_at/);

  const dir1 = new URL(page.url()).searchParams.get('sort_dir');
  expect(['asc', 'desc']).toContain(dir1);

  // Second click on same field should toggle direction
  await page.getByTestId('sort-created_at').click();
  const dir2 = new URL(page.url()).searchParams.get('sort_dir');
  expect(dir2).not.toEqual(dir1);
});

// ---------------------------------------------------------------------------
// AC-10.7  Empty state when no results
// ---------------------------------------------------------------------------

test('AC-10.7: empty state is displayed when no tenants match filters', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockTenantsApi(page, EMPTY_FIXTURE);

  await page.goto('/admin/tenants');

  await expect(page.getByTestId('empty-state')).toBeVisible();
  await expect(page.getByTestId('tenant-table')).not.toBeAttached();
});
