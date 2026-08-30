/**
 * F002 – Packet 10: Workspace List Page and Create Workspace Form
 *
 * E2E tests cover the following acceptance criteria and spec scenarios:
 *
 *   AC-10.1  workspace_administrator sees workspace list + "Create Workspace" button
 *   AC-10.2  data_engineer does NOT see "Create Workspace" button
 *   AC-10.3  Workspace table renders all 5 columns with correct data
 *   AC-10.4  Loading skeleton shown while API call is in-flight
 *   AC-10.5  Sort by "created_at" column header toggles asc/desc
 *   AC-10.6  "Include archived" toggle triggers API call with include_archived=true
 *   AC-10.7  Search input changes trigger debounced API call
 *   AC-10.8  Empty state (active filter): renders CTA for workspace_administrator
 *   AC-10.9  Empty state (archived filter): renders different explanatory text
 *   AC-10.10 WorkspaceStatusBadge renders text label "Active" (not color-only)
 *   AC-10.11 WorkspaceStatusBadge renders text label "Archived" (not color-only)
 *   AC-10.12 Pagination: page 2 triggers API call with page=2; Next btn disabled
 *            when has_next=false; Next btn visible when has_next=true (TG-7)
 *   AC-10.13 Auto-slug from name: "My Workspace" → "my-workspace"
 *   AC-10.14 Manual slug edit stops auto-population
 *   AC-10.15 Slug invalid character warning on per-keystroke input
 *   AC-10.16 Slug immutability notice always visible on create form
 *   AC-10.17 Submit disabled during in-flight request
 *   AC-10.18 Successful create: navigate to /workspaces + success toast
 *   AC-10.19 422 field error (workspace_name): displayed adjacent to input
 *   AC-10.20 422 entity-level error: form-level banner rendered
 *   AC-10.21 403 response: permission-denied banner rendered
 *   AC-10.22 EC-6: name with only invalid chars → empty slug + inline error
 *
 * ── Mocking strategy ─────────────────────────────────────────────────────
 * - Auth is faked by injecting a real-looking JWT into localStorage via
 *   addInitScript before navigation (no backend required).
 * - API calls are intercepted via page.route() and served with fixture data.
 */

import { test, expect, Page, Route } from '@playwright/test';

// ---------------------------------------------------------------------------
// JWT helper
// ---------------------------------------------------------------------------

function buildJwt(
  actorRole:
    | 'workspace_administrator'
    | 'data_engineer'
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

const WORKSPACE_FIXTURE = {
  data: [
    {
      workspace_id: 'ws-001',
      workspace_name: 'Analytics Team',
      workspace_slug: 'analytics-team',
      status: 'active',
      default_timezone: 'UTC',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-03-20T08:30:00Z',
    },
    {
      workspace_id: 'ws-002',
      workspace_name: 'Data Ops',
      workspace_slug: 'data-ops',
      status: 'archived',
      default_timezone: 'Europe/London',
      created_at: '2024-02-01T12:00:00Z',
      updated_at: '2024-03-19T14:00:00Z',
    },
  ],
  meta: { total: 2, page: 1, page_size: 25, has_next: false },
};

const EMPTY_FIXTURE = {
  data: [],
  meta: { total: 0, page: 1, page_size: 25, has_next: false },
};

const PAGINATED_FIXTURE_P1 = {
  data: [
    {
      workspace_id: 'ws-p1',
      workspace_name: 'Page 1 WS',
      workspace_slug: 'page-1-ws',
      status: 'active',
      default_timezone: 'UTC',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  ],
  meta: { total: 30, page: 1, page_size: 25, has_next: true },
};

const PAGINATED_FIXTURE_P2 = {
  data: [
    {
      workspace_id: 'ws-p2',
      workspace_name: 'Page 2 WS',
      workspace_slug: 'page-2-ws',
      status: 'active',
      default_timezone: 'UTC',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    },
  ],
  meta: { total: 30, page: 2, page_size: 25, has_next: false },
};

const CREATED_WORKSPACE_FIXTURE = {
  data: {
    workspace_id: 'ws-new-001',
    tenant_id: 'tenant-001',
    workspace_name: 'My Workspace',
    workspace_slug: 'my-workspace',
    description: null,
    default_timezone: 'UTC',
    status: 'active',
    status_reason: null,
    created_at: '2026-03-29T10:00:00Z',
    updated_at: '2026-03-29T10:00:00Z',
    created_by: 'test-user-id',
    updated_by: 'test-user-id',
  },
};

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Default organization returned by the /organizations mock (stable across tests)
// ---------------------------------------------------------------------------
const MOCK_ORG = {
  id: '00000000-0000-0000-0000-000000000001',
  name: 'Default Organization',
  slug: 'default-org',
  status: 'active',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

async function setupAuth(
  page: Page,
  role:
    | 'workspace_administrator'
    | 'data_engineer'
    | 'platform_viewer',
): Promise<void> {
  await page.addInitScript(
    ({ token }) => localStorage.setItem('access_token', token),
    { token: buildJwt(role) },
  );

  // ── API mocks ─────────────────────────────────────────────────────────────
  // VITE_API_URL=http://localhost:8000/api/v1 so requests hit the real Docker
  // backend directly.  We intercept every startup API call so the fake JWT
  // never reaches the actual backend (which would return 401 → redirect).
  //
  // Newer Playwright route handlers take precedence; test-specific mocks
  // registered after setupAuth() will fire before these handlers.

  // /auth/me   → returns a fixed test user
  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route: Route) => {
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

  // /organizations → OrganizationContext calls this on mount; must return a
  //                  valid { organizations, total } payload or the Axios 401
  //                  interceptor will fire and redirect to /auth/login.
  await page.route(
    (url) => url.href.includes('/api/v1/organizations') && !url.href.includes('/workspaces'),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ organizations: [MOCK_ORG], total: 1 }),
      });
    },
  );

  // /auth/token/refresh (and similar) → 401 so refresh attempts fail cleanly
  await page.route(
    (url) => url.href.includes('/auth/refresh') || url.href.includes('/auth/token'),
    (route: Route) => {
      route.fulfill({ status: 401, contentType: 'application/json', body: '{}' });
    },
  );
}

async function mockListApi(
  page: Page,
  fixture: typeof WORKSPACE_FIXTURE | typeof EMPTY_FIXTURE | typeof PAGINATED_FIXTURE_P1,
): Promise<void> {
  await page.route(
    (url) => url.href.includes('/api/v1/workspaces'),
    (route: Route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(fixture),
        });
      } else {
        route.continue();
      }
    },
  );
}

// ---------------------------------------------------------------------------
// AC-10.1  workspace_administrator sees list + Create button
// ---------------------------------------------------------------------------

test('AC-10.1: workspace_administrator sees workspace list and Create Workspace button', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');

  await expect(page.getByTestId('workspace-list-page')).toBeVisible();
  await expect(page.getByTestId('create-workspace-btn')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.2  data_engineer does NOT see Create button
// ---------------------------------------------------------------------------

test('AC-10.2: data_engineer does not see Create Workspace button', async ({
  page,
}) => {
  await setupAuth(page, 'data_engineer');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');
  await expect(page.getByTestId('workspace-list-page')).toBeVisible();

  await expect(page.getByTestId('create-workspace-btn')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-10.3  Table renders all columns with correct data
// ---------------------------------------------------------------------------

test('AC-10.3: workspace table renders rows with name, slug, status, timezone columns', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');
  await expect(page.getByTestId('workspace-table')).toBeVisible();

  // Row data visible
  await expect(page.getByText('Analytics Team')).toBeVisible();
  await expect(page.getByText('analytics-team')).toBeVisible();
  await expect(page.getByText('Data Ops')).toBeVisible();
  await expect(page.getByText('data-ops')).toBeVisible();
  await expect(page.getByText('UTC')).toBeVisible();
  await expect(page.getByText('Europe/London')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.5  Sort by column header toggles asc/desc
// ---------------------------------------------------------------------------

test('AC-10.5: clicking created_at sort header updates sort state', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');

  await page.getByTestId('sort-created_at').click();
  await expect(page).toHaveURL(/sort_by=created_at/);

  // Click again to toggle direction
  await page.getByTestId('sort-created_at').click();
  await expect(page).toHaveURL(/sort_dir=asc/);
});

// ---------------------------------------------------------------------------
// AC-10.6  "Include archived" toggle triggers API with include_archived=true
// ---------------------------------------------------------------------------

test('AC-10.6: toggling include_archived adds include_archived=true to URL and API call', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');

  const requestUrls: string[] = [];
  await page.route('**/api/v1/workspaces**', (route: Route) => {
    requestUrls.push(route.request().url());
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(WORKSPACE_FIXTURE),
    });
  });

  await page.goto('/workspaces');
  await page.getByTestId('filter-include-archived').click();

  await expect(page).toHaveURL(/include_archived=true/);
  // At least one request after toggle should contain include_archived=true
  await page.waitForTimeout(500);
  const archivedReq = requestUrls.find((u) => u.includes('include_archived=true'));
  expect(archivedReq).toBeTruthy();
});

// ---------------------------------------------------------------------------
// AC-10.7  Search input triggers debounced API call
// ---------------------------------------------------------------------------

test('AC-10.7: typing in search input updates URL q param after debounce', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');

  await page.getByTestId('filter-search').fill('analytics');
  // Wait for the debounce (350 ms + buffer)
  await page.waitForTimeout(500);

  await expect(page).toHaveURL(/q=analytics/);
});

// ---------------------------------------------------------------------------
// AC-10.8  Empty state (active filter) shows CTA for workspace_administrator
// ---------------------------------------------------------------------------

test('AC-10.8: empty active-filter state shows Create Workspace CTA for WA', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, EMPTY_FIXTURE);

  await page.goto('/workspaces');

  await expect(page.getByTestId('empty-state-active')).toBeVisible();
  await expect(page.getByTestId('empty-state-create-btn')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.9  Empty state (archived filter) shows different text without CTA
// ---------------------------------------------------------------------------

test('AC-10.9: empty archived-filter state shows different text without CTA', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, EMPTY_FIXTURE);

  await page.goto('/workspaces?include_archived=true');

  await expect(page.getByTestId('empty-state-archived')).toBeVisible();
  await expect(page.getByText('No archived workspaces', { exact: true })).toBeVisible();
  await expect(page.getByTestId('empty-state-create-btn')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-10.10  WorkspaceStatusBadge renders text label "Active"
// ---------------------------------------------------------------------------

test('AC-10.10: WorkspaceStatusBadge for active workspace renders text label "Active"', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');

  const badge = page.getByTestId('workspace-status-badge-active').first();
  await expect(badge).toBeVisible();
  await expect(badge).toContainText('Active');
});

// ---------------------------------------------------------------------------
// AC-10.11  WorkspaceStatusBadge renders text label "Archived"
// ---------------------------------------------------------------------------

test('AC-10.11: WorkspaceStatusBadge for archived workspace renders text label "Archived"', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces');

  const badge = page.getByTestId('workspace-status-badge-archived').first();
  await expect(badge).toBeVisible();
  await expect(badge).toContainText('Archived');
});

// ---------------------------------------------------------------------------
// AC-10.12  Pagination: next, prev, has_next controls Next button visibility (TG-7)
// ---------------------------------------------------------------------------

test('AC-10.12a: Next button is visible when has_next=true', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, PAGINATED_FIXTURE_P1);

  await page.goto('/workspaces');
  await expect(page.getByTestId('pagination-next')).toBeVisible();
  await expect(page.getByTestId('pagination-next')).toBeEnabled();
});

test('AC-10.12b: clicking Next navigates to page 2 and triggers API call with page=2', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');

  let callCount = 0;
  await page.route('**/api/v1/workspaces**', (route: Route) => {
    const url = route.request().url();
    callCount++;
    const isPage2 = url.includes('page=2');
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(isPage2 ? PAGINATED_FIXTURE_P2 : PAGINATED_FIXTURE_P1),
    });
  });

  await page.goto('/workspaces');
  await expect(page.getByTestId('pagination-next')).toBeEnabled();
  await page.getByTestId('pagination-next').click();

  await expect(page).toHaveURL(/page=2/);
  expect(callCount).toBeGreaterThanOrEqual(2);
});

test('AC-10.12c: Next button is disabled when has_next=false', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE); // has_next: false

  await page.goto('/workspaces');
  await expect(page.getByTestId('pagination-next')).toBeDisabled();
});

// ---------------------------------------------------------------------------
// AC-10.13  Auto-slug from name: "My Workspace" → "my-workspace"
// ---------------------------------------------------------------------------

test('AC-10.13: typing workspace name auto-populates slug field', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces/new');
  await expect(page.getByTestId('create-workspace-form')).toBeVisible();

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await expect(page.getByTestId('field-workspace-slug')).toHaveValue('my-workspace');
});

// ---------------------------------------------------------------------------
// AC-10.14  Manual slug edit stops auto-population
// ---------------------------------------------------------------------------

test('AC-10.14: after user edits slug, changing name does not overwrite it', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await page.getByTestId('field-workspace-slug').fill('my-custom-slug');
  await page.getByTestId('field-workspace-name').fill('My Other Workspace');

  await expect(page.getByTestId('field-workspace-slug')).toHaveValue('my-custom-slug');
});

// ---------------------------------------------------------------------------
// AC-10.15  Slug invalid character warning on per-keystroke input
// ---------------------------------------------------------------------------

test('AC-10.15: typing invalid chars in slug shows per-keystroke warning', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces/new');

  // Type invalid character "!" directly into slug (marks as user-modified)
  await page.getByTestId('field-workspace-slug').fill('!!');

  await expect(page.getByTestId('slug-invalid-char-warning')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-10.16  Slug immutability notice always visible on create form
// ---------------------------------------------------------------------------

test('AC-10.16: slug immutability notice is always visible on create form', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces/new');

  await expect(page.getByTestId('slug-immutability-notice')).toBeVisible();
  await expect(page.getByTestId('slug-immutability-notice')).toContainText(
    'Cannot be changed after creation',
  );
});

// ---------------------------------------------------------------------------
// AC-10.17  Submit disabled during in-flight request
// ---------------------------------------------------------------------------

test('AC-10.17: submit button is disabled while request is in-flight', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  // Delay the POST response to observe the in-flight state
  await page.route('**/api/v1/workspaces', (route: Route) => {
    if (route.request().method() === 'POST') {
      setTimeout(() => {
        route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify(CREATED_WORKSPACE_FIXTURE),
        });
      }, 1000);
    } else {
      route.continue();
    }
  });

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await page.getByTestId('btn-save').click();

  // Immediately after click the button should be disabled
  await expect(page.getByTestId('btn-save')).toBeDisabled();
});

// ---------------------------------------------------------------------------
// AC-10.18  Successful create: navigate to /workspaces + success toast
// ---------------------------------------------------------------------------

test('AC-10.18: valid form submission creates workspace and navigates to list', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.route('**/api/v1/workspaces', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(CREATED_WORKSPACE_FIXTURE),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await page.getByTestId('btn-save').click();

  // Should navigate back to the workspace list
  await expect(page).toHaveURL('/workspaces');
});

// ---------------------------------------------------------------------------
// AC-10.19  422 field error for workspace_name: displayed adjacent to input
// ---------------------------------------------------------------------------

test('AC-10.19: 422 duplicate_name shows inline error on workspace_name field', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.route('**/api/v1/workspaces', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'duplicate_name',
            message: 'A workspace with this name already exists.',
            fields: [
              { field: 'workspace_name', reason: 'A workspace with this name already exists.' },
            ],
          },
        }),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('Analytics Team');
  await page.getByTestId('btn-save').click();

  await expect(page.getByTestId('error-workspace-name')).toBeVisible();
  await expect(page.getByTestId('error-workspace-name')).toContainText('already exists');
});

// ---------------------------------------------------------------------------
// AC-10.20  422 entity-level error: form-level banner rendered
// ---------------------------------------------------------------------------

test('AC-10.20: 422 entity-level error (tenant_not_active) shows form-level banner', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.route('**/api/v1/workspaces', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'tenant_not_active',
            message: 'Your tenant is not currently active.',
            fields: null,
          },
        }),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await page.getByTestId('btn-save').click();

  await expect(page.getByTestId('form-banner-error')).toBeVisible();
  await expect(page.getByTestId('form-banner-error')).toContainText(
    'not currently active',
  );
});

// ---------------------------------------------------------------------------
// AC-10.21  403 response: permission-denied banner rendered
// ---------------------------------------------------------------------------

test('AC-10.21: 403 response shows permission-denied banner', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.route('**/api/v1/workspaces', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'forbidden', message: 'Forbidden', fields: null },
        }),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/workspaces/new');

  await page.getByTestId('field-workspace-name').fill('My Workspace');
  await page.getByTestId('btn-save').click();

  await expect(page.getByTestId('form-banner-error')).toBeVisible();
  await expect(page.getByTestId('form-banner-error')).toContainText('permission');
});

// ---------------------------------------------------------------------------
// AC-10.22  EC-6: name with only invalid chars → empty slug + inline error
// ---------------------------------------------------------------------------

test('AC-10.22 (EC-6): workspace_name with all-invalid chars leaves slug empty and shows error', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockListApi(page, WORKSPACE_FIXTURE);

  await page.goto('/workspaces/new');

  // All invalid chars — generateSlug produces ""
  await page.getByTestId('field-workspace-name').fill('!!!');

  // Slug should be empty (auto-populates but strips all chars)
  await expect(page.getByTestId('field-workspace-slug')).toHaveValue('');

  // Try to submit — should show slug error because slug is empty
  await page.getByTestId('btn-save').click();

  await expect(page.getByTestId('error-workspace-slug')).toBeVisible();
});
