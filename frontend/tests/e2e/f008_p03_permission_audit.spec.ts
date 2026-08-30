/**
 * F008 — Packet 03: Permission Audit Frontend E2E
 *
 * Covers acceptance criteria:
 *   AT-001  Page loads and displays table entries for view_audit_logs user
 *   AT-002  Applying a filter updates URL search parameters
 *   AT-003  Reloading with filter params in URL restores filter inputs
 *   AT-004  Clearing filters removes all filter params from the URL
 *   AT-005  Export CSV button triggers a fetch-based file download
 *   AT-006  actor_type=system rows render a 'System' badge in the Actor cell
 *   AT-007  Zero items renders the empty-state message instead of a table
 *   AT-008  Clicking Occurred At header toggles sort_dir in URL params
 *   AT-009  Pagination Next/Prev controls update the 'page' URL param
 *   AT-010  Actor text input debounces — API not called synchronously on keypress
 *
 * Mocking strategy:
 *   - JWT injected into localStorage via page.addInitScript()
 *   - All API calls intercepted via function-based page.route() matchers
 *   - The audit list endpoint is mocked for all navigation tests
 */

import { test, expect, type Page } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const WS_ID = '00000000-0000-0000-0000-000000000001';
const ACTOR_ID = 'user-001';
const TENANT_ID = '00000000-0000-0000-0000-000000000099';
const AUDIT_PAGE_URL = `/workspaces/${WS_ID}/audit`;
const API_BASE = 'http://localhost:8000/api/v1';

// ─────────────────────────────────────────────────────────────────────────────
// Fixtures
// ─────────────────────────────────────────────────────────────────────────────

const SAMPLE_ENTRIES = [
  {
    log_id: 'aaaa0000-0000-0000-0000-000000000001',
    occurred_at: '2026-03-30T12:00:00Z',
    action_type: 'role_assigned',
    actor_id: 'user-001',
    actor_display_name: 'Alice Admin',
    actor_role: 'workspace_administrator',
    actor_type: 'user',
    target_entity_type: 'workspace_member',
    target_entity_id: 'user-002',
    target_display_name: 'Bob Builder',
    workspace_id: WS_ID,
    request_id: null,
  },
  {
    log_id: 'aaaa0000-0000-0000-0000-000000000002',
    occurred_at: '2026-03-30T11:00:00Z',
    action_type: 'team_created',
    actor_id: null,
    actor_display_name: null,
    actor_role: 'system',
    actor_type: 'system',
    target_entity_type: 'team',
    target_entity_id: 'team-001',
    target_display_name: 'DQ Team Alpha',
    workspace_id: WS_ID,
    request_id: null,
  },
];

const SAMPLE_PAGE = {
  items: SAMPLE_ENTRIES,
  total: 2,
  page: 1,
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

// ─────────────────────────────────────────────────────────────────────────────
// JWT helper
// ─────────────────────────────────────────────────────────────────────────────

function buildJwt(
  actorId = ACTOR_ID,
  actorRole = 'workspace_administrator',
  tenantId = TENANT_ID,
): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      actor_id: actorId,
      actor_role: actorRole,
      tenant_id: tenantId,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth helper
// ─────────────────────────────────────────────────────────────────────────────

async function setupAuth(
  page: Page,
  actorRole = 'workspace_administrator',
  actorId = ACTOR_ID,
): Promise<void> {
  const token = buildJwt(actorId, actorRole);

  await page.addInitScript(
    ({ t }: { t: string }) => {
      localStorage.setItem('access_token', t);
    },
    { t: token },
  );

  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: actorId,
          email: 'actor@example.com',
          full_name: 'Test Actor',
          avatar_url: null,
          email_verified: true,
          status: 'active',
          last_login_at: null,
          created_at: '2024-01-01T00:00:00Z',
        }),
      });
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Audit API mock helper
// ─────────────────────────────────────────────────────────────────────────────

async function mockAuditList(
  page: Page,
  responseBody: object = SAMPLE_PAGE,
  captureRequest?: { url: string },
): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}/audit/permissions`) &&
      !url.href.includes('/export'),
    (route) => {
      if (route.request().method() === 'GET') {
        if (captureRequest) {
          captureRequest.url = route.request().url();
        }
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(responseBody),
        });
      } else {
        route.fallback();
      }
    },
  );
}

async function mockAuditExport(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}/audit/permissions/export`),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'text/csv',
          body: 'occurred_at,action_type,actor,target,actor_role\n',
          headers: {
            'Content-Disposition': `attachment; filename="permission-audit-${WS_ID}.csv"`,
          },
        });
      } else {
        route.fallback();
      }
    },
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// AT-001  Page loads and displays entries
// ═════════════════════════════════════════════════════════════════════════════

test('AT-001: page loads and renders audit entries in the table', async ({ page }) => {
  await setupAuth(page);
  await mockAuditList(page);

  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('permission-audit-page')).toBeVisible();
  await expect(page.getByTestId('audit-table')).toBeVisible();

  // Both sample rows should appear
  const rows = page.getByTestId('audit-table-row');
  await expect(rows).toHaveCount(2);

  // First row contains 'role assigned' (action_type rendered with spaces)
  await expect(rows.first()).toContainText('role assigned');
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-002  Filter selection updates URL params immediately (action_type dropdown)
// ═════════════════════════════════════════════════════════════════════════════

test('AT-002: selecting action_type filter appends it to the URL', async ({ page }) => {
  await setupAuth(page);
  await mockAuditList(page);

  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('action-type-select')).toBeVisible();

  await page.getByTestId('action-type-select').selectOption('role_assigned');

  await expect(page).toHaveURL(/action_type=role_assigned/);
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-003  Reloading with filter params restores filter input values
// ═════════════════════════════════════════════════════════════════════════════

test('AT-003: navigating to audit page with URL filter params restores input values', async ({
  page,
}) => {
  await setupAuth(page);
  await mockAuditList(page);

  // Navigate directly with an action_type param in the URL
  await page.goto(`${AUDIT_PAGE_URL}?action_type=role_assigned&sort_dir=asc`);
  await expect(page.getByTestId('permission-audit-filters')).toBeVisible();

  // The action_type select should reflect the URL param
  await expect(page.getByTestId('action-type-select')).toHaveValue('role_assigned');
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-004  Clear Filters removes all URL params
// ═════════════════════════════════════════════════════════════════════════════

test('AT-004: clicking Clear Filters removes filter params from the URL', async ({ page }) => {
  await setupAuth(page);
  await mockAuditList(page);

  // Start with a filter applied
  await page.goto(`${AUDIT_PAGE_URL}?action_type=role_assigned`);
  await expect(page.getByTestId('action-type-select')).toHaveValue('role_assigned');

  await page.getByTestId('clear-filters-btn').click();

  // URL should no longer contain action_type
  await expect(page).not.toHaveURL(/action_type=/);
  // Input should be reset to empty
  await expect(page.getByTestId('action-type-select')).toHaveValue('');
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-005  Export CSV button triggers a fetch-based download
// ═════════════════════════════════════════════════════════════════════════════

test('AT-005: Export CSV button triggers an authenticated fetch to the export endpoint', async ({
  page,
}) => {
  await setupAuth(page);
  await mockAuditList(page);

  let exportFetchMade = false;
  let authHeaderPresent = false;

  await page.route(
    (url) => url.href.includes(`/api/v1/workspaces/${WS_ID}/audit/permissions/export`),
    (route) => {
      exportFetchMade = true;
      const authHeader = route.request().headers()['authorization'] ?? '';
      authHeaderPresent = authHeader.startsWith('Bearer ');
      route.fulfill({
        status: 200,
        contentType: 'text/csv',
        body: 'occurred_at,action_type\n',
        headers: {
          'Content-Disposition': `attachment; filename="audit.csv"`,
        },
      });
    },
  );

  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('export-csv-btn')).toBeVisible();
  await page.getByTestId('export-csv-btn').click();

  // Allow the fetch to complete
  await page.waitForTimeout(500);

  expect(exportFetchMade).toBe(true);
  expect(authHeaderPresent).toBe(true);
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-006  actor_type=system rows render 'System' badge
// ═════════════════════════════════════════════════════════════════════════════

test('AT-006: actor_type=system entry renders a System badge in the Actor cell', async ({
  page,
}) => {
  await setupAuth(page);
  await mockAuditList(page);

  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('audit-table')).toBeVisible();

  // Second sample entry has actor_type=system
  const badge = page.getByTestId('system-actor-badge');
  await expect(badge).toBeVisible();
  await expect(badge).toContainText('System');
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-007  Empty results show the empty-state message
// ═════════════════════════════════════════════════════════════════════════════

test('AT-007: zero matching entries renders the empty-state message', async ({ page }) => {
  await setupAuth(page);
  await mockAuditList(page, EMPTY_PAGE);

  await page.goto(AUDIT_PAGE_URL);

  await expect(page.getByTestId('audit-table-empty')).toBeVisible();
  await expect(page.getByTestId('audit-table-empty')).toContainText(
    'No access-change events found',
  );
  // The table element itself should not be present in empty state
  await expect(page.getByTestId('audit-table')).not.toBeVisible();
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-008  Clicking Occurred At header toggles sort_dir in the URL
// ═════════════════════════════════════════════════════════════════════════════

test('AT-008: clicking Occurred At column header toggles sort_dir URL param', async ({
  page,
}) => {
  await setupAuth(page);
  await mockAuditList(page);

  // Start with default desc sort
  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('audit-table')).toBeVisible();

  // Click the sort button — should toggle to asc
  await page.getByTestId('occurred-at-sort-btn').click();
  await expect(page).toHaveURL(/sort_dir=asc/);

  // Click again — should toggle back to desc
  await page.getByTestId('occurred-at-sort-btn').click();
  await expect(page).toHaveURL(/sort_dir=desc/);
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-009  Pagination Next/Prev update the page URL param
// ═════════════════════════════════════════════════════════════════════════════

test('AT-009: Next and Prev pagination buttons update the page URL param', async ({ page }) => {
  await setupAuth(page);

  // Return has_next=true so Next button is enabled
  await mockAuditList(page, {
    items: SAMPLE_ENTRIES,
    total: 100,
    page: 1,
    page_size: 25,
    has_next: true,
  });

  await page.goto(AUDIT_PAGE_URL);
  await expect(page.getByTestId('pagination-controls')).toBeVisible();

  const nextBtn = page.getByTestId('next-page-btn');
  await expect(nextBtn).not.toBeDisabled();
  await nextBtn.click();

  await expect(page).toHaveURL(/page=2/);

  const prevBtn = page.getByTestId('prev-page-btn');
  await expect(prevBtn).not.toBeDisabled();
  await prevBtn.click();

  await expect(page).toHaveURL(/page=1/);
});

// ═════════════════════════════════════════════════════════════════════════════
// AT-010  Actor text input debounces — API not called synchronously
// ═════════════════════════════════════════════════════════════════════════════

test('AT-010: actor ID input debounces — API is not called within 100ms of keypress', async ({
  page,
}) => {
  await setupAuth(page);

  let requestCount = 0;

  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}/audit/permissions`) &&
      !url.href.includes('/export'),
    (route) => {
      requestCount++;
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SAMPLE_PAGE),
      });
    },
  );

  await page.goto(AUDIT_PAGE_URL);
  // Wait for initial fetch to settle
  await page.waitForTimeout(400);
  const countAfterLoad = requestCount;

  // Type into actor input — within debounce window (300ms) no extra call should fire
  await page.getByTestId('actor-id-input').fill('some-uuid-value');
  await page.waitForTimeout(100); // wait only 100ms (well within 300ms debounce)

  expect(requestCount).toBe(countAfterLoad); // No extra call fired within 100ms
});

// ═════════════════════════════════════════════════════════════════════════════
// Additional: Filter via API — verify URL params are forwarded to fetch call
// ═════════════════════════════════════════════════════════════════════════════

test('AT-011 (supplemental): filter params in URL are forwarded to the API request', async ({
  page,
}) => {
  const captured: { url: string } = { url: '' };

  await setupAuth(page);
  await mockAuditList(page, SAMPLE_PAGE, captured);

  await page.goto(
    `${AUDIT_PAGE_URL}?action_type=role_assigned&sort_dir=desc&page=1`,
  );
  await expect(page.getByTestId('audit-table')).toBeVisible();

  // The captured request URL should include the filter param
  const fetchUrl = new URL(captured.url, API_BASE);
  expect(fetchUrl.searchParams.get('action_type')).toBe('role_assigned');
  expect(fetchUrl.searchParams.get('sort_dir')).toBe('desc');
});
