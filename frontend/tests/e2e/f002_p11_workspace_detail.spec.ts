/**
 * F002 – Packet 11: Workspace Detail Page, Edit, Archive, and Restore
 *
 * E2E tests cover the following acceptance criteria:
 *
 *   AC-11.1  workspace_detail_page renders all workspace metadata
 *   AC-11.2  data_engineer does NOT see Archive button or Edit form
 *   AC-11.3  workspace_administrator sees Archive button (active workspace)
 *   AC-11.4  workspace_administrator sees Restore button (archived workspace)
 *   AC-11.5  EditWorkspaceForm pre-fills current values; immutable fields read-only
 *   AC-11.6  Successful edit → success toast + updated name visible
 *   AC-11.7  422 field error on edit → error displayed adjacent to field
 *   AC-11.8  Archive modal requires status_reason (empty → error)
 *   AC-11.9  Successful archive → detail page shows Archived status badge
 *   AC-11.10 Archive 409 last_active_workspace → warning + checkbox revealed;
 *             submit blocked until checkbox checked (reactive model)
 *   AC-11.11 Archive confirm last_active_workspace with checkbox → success toast
 *   AC-11.12 Restore confirmation → Restore button pressed → success toast
 *   AC-11.13 Restore with tenant_not_active → 422 error shown in modal
 *   AC-11.14 Audit log panel link is visible on detail page
 *
 * ── Mocking strategy ────────────────────────────────────────────────────
 * Same as P10: function-based page.route() matchers for all API calls to
 * prevent the fake JWT from hitting the Docker backend.
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

const WS_ID = 'ws-detail-001';

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

const ARCHIVED_WORKSPACE = {
  ...ACTIVE_WORKSPACE,
  status: 'archived',
  status_reason: 'Project completed',
};

const ACTIVE_WORKSPACE_RESPONSE = { data: ACTIVE_WORKSPACE };
const ARCHIVED_WORKSPACE_RESPONSE = { data: ARCHIVED_WORKSPACE };

// ---------------------------------------------------------------------------
// Setup helpers
// ---------------------------------------------------------------------------

async function setupAuth(
  page: Page,
  role: 'workspace_administrator' | 'data_engineer' | 'platform_viewer',
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

/** Mock GET /workspaces/{id} with a given fixture. */
async function mockGetWorkspace(
  page: Page,
  fixture: typeof ACTIVE_WORKSPACE_RESPONSE | typeof ARCHIVED_WORKSPACE_RESPONSE,
): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}`) &&
      !url.href.includes('/archive') &&
      !url.href.includes('/restore'),
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

const DETAIL_URL = `/workspaces/${WS_ID}`;

// ---------------------------------------------------------------------------
// AC-11.1  Detail page renders all workspace metadata
// ---------------------------------------------------------------------------

test('AC-11.1: workspace detail page renders all workspace metadata', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('workspace-detail-card')).toBeVisible();
  await expect(page.getByTestId('workspace-detail-name')).toHaveText('Analytics Team');
  await expect(page.getByTestId('workspace-detail-slug')).toHaveText('analytics-team');
  await expect(page.getByTestId('workspace-detail-id')).toHaveText(WS_ID);
  await expect(page.getByTestId('workspace-detail-tenant-id')).toHaveText('tenant-001');
  // Status badge
  await expect(page.getByRole('status')).toHaveText(/Active/i);
});

// ---------------------------------------------------------------------------
// AC-11.2  data_engineer does NOT see Archive button or Edit form
// ---------------------------------------------------------------------------

test('AC-11.2: data_engineer does not see Archive button or Edit form', async ({ page }) => {
  await setupAuth(page, 'data_engineer');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('workspace-detail-card')).toBeVisible();
  await expect(page.getByTestId('archive-workspace-btn')).not.toBeVisible();
  await expect(page.getByTestId('edit-workspace-form')).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.3  workspace_administrator sees Archive button (active workspace)
// ---------------------------------------------------------------------------

test('AC-11.3: workspace_administrator sees Archive button for active workspace', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('archive-workspace-btn')).toBeVisible();
  await expect(page.getByTestId('restore-workspace-btn')).not.toBeVisible();
  await expect(page.getByTestId('edit-workspace-form')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.4  workspace_administrator sees Restore button (archived workspace)
// ---------------------------------------------------------------------------

test('AC-11.4: workspace_administrator sees Restore button for archived workspace', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ARCHIVED_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('restore-workspace-btn')).toBeVisible();
  await expect(page.getByTestId('archive-workspace-btn')).not.toBeVisible();
  // Edit form hidden for archived workspace
  await expect(page.getByTestId('edit-workspace-form')).not.toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.5  EditWorkspaceForm pre-fills current values; immutable fields read-only
// ---------------------------------------------------------------------------

test('AC-11.5: EditWorkspaceForm pre-fills values and shows immutable fields as read-only', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  const form = page.getByTestId('edit-workspace-form');
  await expect(form).toBeVisible();

  // Pre-filled editable fields
  await expect(page.getByTestId('edit-workspace-name-input')).toHaveValue('Analytics Team');
  await expect(page.getByTestId('edit-workspace-description-input')).toHaveValue(
    'Main analytics workspace',
  );

  // Read-only identity fields (rendered as divs, not inputs)
  const idField = page.getByTestId('edit-workspace-id-readonly');
  const slugField = page.getByTestId('edit-workspace-slug-readonly');
  const tenantField = page.getByTestId('edit-workspace-tenant-id-readonly');

  await expect(idField).toHaveText(WS_ID);
  await expect(slugField).toHaveText('analytics-team');
  await expect(tenantField).toHaveText('tenant-001');
});

// ---------------------------------------------------------------------------
// AC-11.6  Successful edit → success toast + updated name visible
// ---------------------------------------------------------------------------

test('AC-11.6: successful edit shows success toast and updated name', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');

  const UPDATED = {
    data: {
      ...ACTIVE_WORKSPACE,
      workspace_name: 'Analytics Team Updated',
    },
  };

  // Single combined handler: GET returns original; PATCH returns updated.
  // Registered once so no LIFO conflict with a second GET handler.
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}`) &&
      !url.href.includes('/archive') &&
      !url.href.includes('/restore'),
    (route: Route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(UPDATED),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ACTIVE_WORKSPACE_RESPONSE),
        });
      }
    },
  );

  await page.goto(DETAIL_URL);

  await page.getByTestId('edit-workspace-name-input').fill('Analytics Team Updated');
  await page.getByTestId('edit-workspace-submit-btn').click();

  await expect(page.getByText('Workspace updated successfully.')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.7  422 field error on edit → error adjacent to field
// ---------------------------------------------------------------------------

test('AC-11.7: 422 field error on edit shows error adjacent to workspace_name', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');

  // Single handler: GET returns fixture; PATCH returns 422.
  // Avoids LIFO conflict (route.continue() for GET would hit real backend → 401).
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}`) &&
      !url.href.includes('/archive') &&
      !url.href.includes('/restore'),
    (route: Route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'validation_error',
              message: 'Validation failed.',
              fields: [{ field: 'workspace_name', reason: 'Name already in use.' }],
            },
          }),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ACTIVE_WORKSPACE_RESPONSE),
        });
      }
    },
  );

  await page.goto(DETAIL_URL);

  await page.getByTestId('edit-workspace-name-input').fill('Duplicate Name');
  await page.getByTestId('edit-workspace-submit-btn').click();

  await expect(page.getByTestId('edit-workspace-name-error')).toHaveText(
    'Name already in use.',
  );
});

// ---------------------------------------------------------------------------
// AC-11.8  Archive modal requires status_reason
// ---------------------------------------------------------------------------

test('AC-11.8: archive modal submit without status_reason shows field error', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await page.getByTestId('archive-workspace-btn').click();
  await expect(page.getByTestId('archive-workspace-modal')).toBeVisible();

  // Click submit without filling reason
  await page.getByTestId('archive-submit-btn').click();

  await expect(page.getByTestId('archive-status-reason-error')).toHaveText(
    'Archive reason is required.',
  );
});

// ---------------------------------------------------------------------------
// AC-11.9  Successful archive → detail page shows Archived status badge
// ---------------------------------------------------------------------------

test('AC-11.9: successful archive shows Archived status badge', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  // Mock POST /archive → 200. No second GET handler needed (mockGetWorkspace handles refetch).
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/archive`),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { ...ACTIVE_WORKSPACE, status: 'archived', status_reason: 'Done' } }),
      });
    },
  );

  await page.goto(DETAIL_URL);
  await page.getByTestId('archive-workspace-btn').click();
  await page.getByTestId('archive-status-reason-input').fill('Done');
  await page.getByTestId('archive-submit-btn').click();

  await expect(page.getByText('Workspace archived successfully.')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.10 Archive 409 last_active_workspace → warning + checkbox revealed
// ---------------------------------------------------------------------------

test('AC-11.10: archive 409 last_active_workspace reveals warning and checkbox', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  // First POST returns 409 last_active_workspace
  let archiveCallCount = 0;
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/archive`),
    (route: Route) => {
      archiveCallCount++;
      if (archiveCallCount === 1) {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'last_active_workspace',
              message: 'This is the last active workspace in the tenant.',
              fields: null,
            },
          }),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            data: { ...ACTIVE_WORKSPACE, status: 'archived', status_reason: 'Solo workspace' },
          }),
        });
      }
    },
  );

  await page.goto(DETAIL_URL);
  await page.getByTestId('archive-workspace-btn').click();
  await page.getByTestId('archive-status-reason-input').fill('Solo workspace');
  await page.getByTestId('archive-submit-btn').click();

  // Warning should appear; modal stays open
  await expect(page.getByTestId('archive-last-workspace-warning')).toBeVisible();
  await expect(page.getByTestId('archive-confirm-last-workspace-checkbox')).toBeVisible();
  // Submit button should still be disabled (checkbox not checked)
  await expect(page.getByTestId('archive-submit-btn')).toBeDisabled();
});

// ---------------------------------------------------------------------------
// AC-11.11 Archive last_active_workspace with checkbox → success
// ---------------------------------------------------------------------------

test('AC-11.11: archive confirms last_active_workspace when checkbox checked', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  let archiveCallCount = 0;
  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/archive`),
    (route: Route) => {
      archiveCallCount++;
      if (archiveCallCount === 1) {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'last_active_workspace',
              message: 'This is the last active workspace.',
              fields: null,
            },
          }),
        });
      } else {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            data: { ...ACTIVE_WORKSPACE, status: 'archived', status_reason: 'Last WS' },
          }),
        });
      }
    },
  );

  await page.goto(DETAIL_URL);
  await page.getByTestId('archive-workspace-btn').click();
  await page.getByTestId('archive-status-reason-input').fill('Last WS');
  await page.getByTestId('archive-submit-btn').click();

  // Wait for warning to appear
  await expect(page.getByTestId('archive-last-workspace-warning')).toBeVisible();

  // Check the confirmation checkbox
  await page.getByTestId('archive-confirm-last-workspace-checkbox').check();
  await expect(page.getByTestId('archive-submit-btn')).toBeEnabled();

  // Second submit
  await page.getByTestId('archive-submit-btn').click();
  await expect(page.getByText('Workspace archived successfully.')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.12 Restore confirmation → success toast
// ---------------------------------------------------------------------------

test('AC-11.12: restore confirmation shows success toast', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ARCHIVED_WORKSPACE_RESPONSE);

  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/restore`),
    (route: Route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { ...ACTIVE_WORKSPACE } }),
      });
    },
  );

  await page.goto(DETAIL_URL);
  await page.getByTestId('restore-workspace-btn').click();
  await expect(page.getByTestId('restore-workspace-modal')).toBeVisible();

  await page.getByTestId('restore-confirm-btn').click();
  await expect(page.getByText('Workspace restored successfully.')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.13 Restore with tenant_not_active → 422 error shown in modal
// ---------------------------------------------------------------------------

test('AC-11.13: restore shows error when tenant is not active', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ARCHIVED_WORKSPACE_RESPONSE);

  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/restore`),
    (route: Route) => {
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'tenant_not_active',
            message: 'Cannot restore: the parent tenant is not active.',
            fields: null,
          },
        }),
      });
    },
  );

  await page.goto(DETAIL_URL);
  await page.getByTestId('restore-workspace-btn').click();
  await page.getByTestId('restore-confirm-btn').click();

  await expect(page.getByTestId('restore-tenant-error')).toHaveText(
    /Cannot restore: the parent tenant is not active\./i,
  );
  // Modal remains open
  await expect(page.getByTestId('restore-workspace-modal')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.14 Audit log panel link is visible
// ---------------------------------------------------------------------------

test('AC-11.14: audit log panel link is visible on detail page', async ({ page }) => {
  await setupAuth(page, 'workspace_administrator');
  await mockGetWorkspace(page, ACTIVE_WORKSPACE_RESPONSE);

  await page.goto(DETAIL_URL);

  await expect(page.getByTestId('audit-log-panel')).toBeVisible();
  await expect(page.getByTestId('audit-log-link')).toBeVisible();
  await expect(page.getByTestId('audit-log-link')).toHaveAttribute(
    'href',
    `/workspaces/${WS_ID}/audit`,
  );
});
