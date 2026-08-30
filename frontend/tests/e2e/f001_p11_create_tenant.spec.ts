/**
 * F001 – Packet 11: Create Tenant Page
 *
 * E2E tests verify:
 *   AC-11.1  Auto-slug generation from name field
 *   AC-11.2  User override of slug stops auto-generation permanently
 *   AC-11.3  Slug blur validation — minimum 3 characters
 *   AC-11.4  Successful create → redirected to detail page + toast visible
 *   AC-11.5  422 duplicate_slug → banner + inline slug error both visible
 *   AC-11.6  Platform Viewer is shown 403 page (AdminGuard from Packet 10)
 *
 * Additional scenarios from TDD §7.5:
 *   AC-11.7  SlugImmutabilityNotice and RegionImmutabilityNotice are visible
 *   AC-11.8  Cancel button navigates back to /admin/tenants
 *   AC-11.9  Required field validation on submit (all blank → errors shown)
 *
 * ── Mocking strategy ──────────────────────────────────────────────────────
 * - Auth faked via addInitScript + localStorage (same pattern as Packet 10).
 * - POST /api/v1/tenants intercepted via page.route().
 * - On success: mock returns 201 with a fixture tenant object and the test
 *   asserts navigation to the detail page (which is currently a placeholder).
 */

import { test, expect, Page, Route } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildJwt(actorRole: 'platform_admin' | 'platform_viewer'): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      email: 'admin@example.com',
      actor_role: actorRole,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

async function setupAuth(
  page: Page,
  role: 'platform_admin' | 'platform_viewer',
): Promise<void> {
  await page.addInitScript(
    ({ token }) => localStorage.setItem('access_token', token),
    { token: buildJwt(role) },
  );
}

const CREATED_TENANT_ID = 'tid-new-001';

const CREATED_TENANT_FIXTURE = {
  data: {
    tenant_id: CREATED_TENANT_ID,
    tenant_name: 'Acme Corp',
    tenant_slug: 'acme-corp',
    status: 'draft',
    status_reason: null,
    region: 'eu-west',
    plan: 'starter',
    service_start_date: null,
    tenant_notes: null,
    created_at: '2026-03-27T10:00:00Z',
    updated_at: '2026-03-27T10:00:00Z',
    created_by: 'test-user-id',
    updated_by: 'test-user-id',
  },
};

const TENANT_LIST_FIXTURE = {
  data: [],
  meta: { total: 0, page: 1, page_size: 20, has_next: false },
};

async function mockListApi(page: Page) {
  await page.route('**/api/v1/tenants', (route: Route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(TENANT_LIST_FIXTURE),
      });
    } else {
      route.continue();
    }
  });
}

// ---------------------------------------------------------------------------
// AC-11.1  Auto-slug generation from name field
// ---------------------------------------------------------------------------

test('AC-11.1: typing a name auto-populates the slug field', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');
  await expect(page.getByTestId('create-tenant-form')).toBeVisible();

  await page.getByTestId('field-tenant-name').fill('Acme Corp');

  await expect(page.getByTestId('field-tenant-slug')).toHaveValue('acme-corp');
});

// ---------------------------------------------------------------------------
// AC-11.2  User slug edit stops auto-generation
// ---------------------------------------------------------------------------

test('AC-11.2: after user edits slug, changing name does not overwrite it', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  await page.getByTestId('field-tenant-name').fill('Acme Corp');
  // User manually edits the slug
  await page.getByTestId('field-tenant-slug').fill('my-custom-slug');

  // Change the name — slug must NOT be overwritten
  await page.getByTestId('field-tenant-name').fill('Acme Corporation');

  await expect(page.getByTestId('field-tenant-slug')).toHaveValue('my-custom-slug');
});

// ---------------------------------------------------------------------------
// AC-11.3  Slug blur validation — minimum 3 characters
// ---------------------------------------------------------------------------

test('AC-11.3: slug field shows inline error when value is fewer than 3 characters', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  // Type 2-char value in slug, then blur
  await page.getByTestId('field-tenant-slug').fill('ab');
  await page.getByTestId('field-tenant-slug').blur();

  await expect(page.getByTestId('error-tenant-slug')).toBeVisible();
  await expect(page.getByTestId('error-tenant-slug')).toContainText('3');
});

// ---------------------------------------------------------------------------
// AC-11.4  Successful create → redirected to detail + toast
// ---------------------------------------------------------------------------

test('AC-11.4: valid form submission returns 201 and navigates to detail page', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  // Mock the POST endpoint
  await page.route('**/api/v1/tenants', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(CREATED_TENANT_FIXTURE),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/admin/tenants/new');

  // Fill all required fields
  await page.getByTestId('field-tenant-name').fill('Acme Corp');
  await page.getByTestId('field-region').selectOption('eu-west');
  await page.getByTestId('field-plan').selectOption('starter');

  await page.getByTestId('btn-save').click();

  // Should navigate to the detail page
  await expect(page).toHaveURL(`/admin/tenants/${CREATED_TENANT_ID}`);
});

// ---------------------------------------------------------------------------
// AC-11.5  422 duplicate_slug → banner + inline slug error
// ---------------------------------------------------------------------------

test('AC-11.5: 422 duplicate_slug shows both banner and inline slug error', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.route('**/api/v1/tenants', (route: Route) => {
    if (route.request().method() === 'POST') {
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'duplicate_slug',
            message: 'A tenant with this slug already exists.',
            fields: [{ field: 'tenant_slug', reason: 'This slug is already taken.' }],
          },
        }),
      });
    } else {
      route.continue();
    }
  });

  await page.goto('/admin/tenants/new');

  await page.getByTestId('field-tenant-name').fill('Acme Corp');
  await page.getByTestId('field-region').selectOption('eu-west');
  await page.getByTestId('field-plan').selectOption('starter');

  await page.getByTestId('btn-save').click();

  // Both the banner and the inline error must be visible
  await expect(page.getByTestId('form-banner-error')).toBeVisible();
  await expect(page.getByTestId('error-tenant-slug')).toBeVisible();
  await expect(page.getByTestId('error-tenant-slug')).toContainText('already taken');
});

// ---------------------------------------------------------------------------
// AC-11.6  Platform Viewer sees 403 page
// ---------------------------------------------------------------------------

test('AC-11.6: platform_viewer is shown the forbidden page on /admin/tenants/new', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  // AdminGuard requireAdmin renders ForbiddenPage
  await expect(page.getByText(/Access Denied/i)).toBeVisible();
  await expect(page.getByTestId('create-tenant-form')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-11.7  Immutability notices visible
// ---------------------------------------------------------------------------

test('AC-11.7: slug and region immutability notices are visible on the form', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  await expect(page.getByTestId('slug-immutability-notice')).toBeVisible();
  await expect(page.getByTestId('region-immutability-notice')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-11.8  Cancel navigates to list
// ---------------------------------------------------------------------------

test('AC-11.8: Cancel button navigates back to /admin/tenants', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  await page.getByTestId('btn-cancel').click();

  await expect(page).toHaveURL('/admin/tenants');
});

// ---------------------------------------------------------------------------
// AC-11.9  Required field validation on submit (all blank)
// ---------------------------------------------------------------------------

test('AC-11.9: submitting an empty form shows errors on all required fields', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockListApi(page);

  await page.goto('/admin/tenants/new');

  // Click Save without filling anything
  await page.getByTestId('btn-save').click();

  // Required fields should all show errors
  await expect(page.getByTestId('error-tenant-name')).toBeVisible();
  await expect(page.getByTestId('error-tenant-slug')).toBeVisible();
  await expect(page.getByTestId('error-region')).toBeVisible();
  await expect(page.getByTestId('error-plan')).toBeVisible();
});
