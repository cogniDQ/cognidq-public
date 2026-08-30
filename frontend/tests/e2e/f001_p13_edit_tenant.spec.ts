/**
 * F001 – Packet 13: Edit Tenant Page and Status Change Modal
 *
 * E2E tests verify:
 *   AC-13.1  Immutable fields (slug, region, tenant_id) are visible but disabled;
 *            mutable fields are editable
 *   AC-13.2  Only changed field is sent in PATCH body
 *   AC-13.3  409 conflict on PATCH → banner, stay on edit page, form values intact
 *   AC-13.4  Suspend button → modal shows StatusReasonInput + session impact text +
 *            Confirm disabled until reason ≥ 10 chars
 *   AC-13.5  Status change 200 → modal closes, detail refreshed, new status shown
 *   AC-13.6  Tab key cycles focus only within modal (focus trap)
 *   AC-13.7  Modal close → focus returns to triggering button
 *
 * Additional coverage:
 *   AC-13.8  Archive button → modal shows reason field + irreversibility note
 *   AC-13.9  Activate button → modal has no reason field shown
 *   AC-13.10 API error on POST /status → modal stays open, error shown inline
 *
 * ── Mocking strategy ───────────────────────────────────────────────────────
 * - Auth faked via addInitScript + localStorage.
 * - GET /api/v1/tenants/:id intercepted per test.
 * - PATCH /api/v1/tenants/:id intercepted per test.
 * - POST /api/v1/tenants/:id/status intercepted per test.
 */

import { test, expect, Page } from '@playwright/test';

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

const TENANT_ID = 'tid-edit-001';

const BASE_TENANT = {
  tenant_id: TENANT_ID,
  tenant_name: 'Acme Corp',
  tenant_slug: 'acme-corp',
  status: 'active',
  status_reason: null,
  region: 'eu-west',
  plan: 'starter',
  service_start_date: null,
  tenant_notes: null,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  created_by: 'admin@example.com',
  updated_by: 'admin@example.com',
  workspace_count: 0,
  workspace_count_available: true,
  user_count: 0,
  user_count_available: true,
  audit_summary_link: `/api/v1/tenants/${TENANT_ID}/audit-logs`,
};

async function mockTenantGet(
  page: Page,
  overrides: Record<string, unknown> = {},
) {
  await page.route(`**/api/v1/tenants/${TENANT_ID}`, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: { ...BASE_TENANT, ...overrides } }),
      });
    } else {
      route.continue();
    }
  });
}

// ---------------------------------------------------------------------------
// AC-13.1 — Read-only fields visible + disabled; mutable fields editable
// ---------------------------------------------------------------------------

test('AC-13.1: immutable fields are disabled, mutable fields are editable', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page);

  await page.goto(`/admin/tenants/${TENANT_ID}/edit`);
  await page.waitForSelector('[data-testid="edit-tenant-form"]');

  // Read-only / disabled
  await expect(page.getByTestId('field-tenant-id-readonly')).toBeDisabled();
  await expect(page.getByTestId('field-tenant-slug-readonly')).toBeDisabled();
  await expect(page.getByTestId('field-region-readonly')).toBeDisabled();

  // Editable
  await expect(page.getByTestId('field-tenant-name')).toBeEditable();
  await expect(page.getByTestId('field-plan')).toBeEnabled();
  await expect(page.getByTestId('field-service-start-date')).toBeEditable();
  await expect(page.getByTestId('field-tenant-notes')).toBeEditable();
});

// ---------------------------------------------------------------------------
// AC-13.2 — Only changed field sent in PATCH body
// ---------------------------------------------------------------------------

test('AC-13.2: only changed fields are sent in PATCH body', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page);

  let patchBody: Record<string, unknown> | null = null;
  await page.route(`**/api/v1/tenants/${TENANT_ID}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      patchBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { ...BASE_TENANT, plan: 'growth' },
        }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto(`/admin/tenants/${TENANT_ID}/edit`);
  await page.waitForSelector('[data-testid="edit-tenant-form"]');

  // Change only the plan field
  await page.getByTestId('field-plan').selectOption('growth');
  await page.getByTestId('btn-save-edit').click();

  // Wait for navigation away (success)
  await page.waitForURL(`**/admin/tenants/${TENANT_ID}`);

  // PATCH body must contain only 'plan'
  expect(patchBody).not.toBeNull();
  expect(Object.keys(patchBody!)).toEqual(['plan']);
  expect(patchBody!['plan']).toBe('growth');
});

// ---------------------------------------------------------------------------
// AC-13.3 — 409 conflict: banner shown, form stays on edit page
// ---------------------------------------------------------------------------

test('AC-13.3: 409 on PATCH shows conflict banner, stays on edit page', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page);

  await page.route(`**/api/v1/tenants/${TENANT_ID}`, async (route) => {
    if (route.request().method() === 'PATCH') {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'conflict', message: 'Conflict detected.' },
        }),
      });
    } else {
      await route.continue();
    }
  });

  await page.goto(`/admin/tenants/${TENANT_ID}/edit`);
  await page.waitForSelector('[data-testid="edit-tenant-form"]');

  // Change name and submit
  await page.getByTestId('field-tenant-name').fill('Updated Name');
  await page.getByTestId('btn-save-edit').click();

  // Banner must appear; page must stay on edit
  await expect(page.getByTestId('edit-form-banner')).toBeVisible();
  expect(page.url()).toContain('/edit');

  // Form value is intact
  await expect(page.getByTestId('field-tenant-name')).toHaveValue('Updated Name');
});

// ---------------------------------------------------------------------------
// AC-13.4 — Suspend modal: reason input shown, confirm disabled until ≥ 10 chars
// ---------------------------------------------------------------------------

test('AC-13.4: suspend modal shows reason input; confirm disabled until 10 chars', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  // Use an active tenant so Suspend button is visible
  await mockTenantGet(page, { status: 'active' });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-suspend"]');

  await page.getByTestId('btn-suspend').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  // Transition summary
  await expect(page.getByTestId('modal-transition-summary')).toContainText('Active');
  await expect(page.getByTestId('modal-transition-summary')).toContainText('Suspended');

  // Session impact text visible
  await expect(page.getByTestId('modal-impact-list')).toContainText('sessions');

  // Reason input visible
  await expect(page.getByTestId('modal-reason-input')).toBeVisible();

  // Confirm disabled with empty reason
  await expect(page.getByTestId('btn-modal-confirm')).toBeDisabled();

  // Type 9 chars — still disabled
  await page.getByTestId('modal-reason-input').fill('123456789');
  await expect(page.getByTestId('btn-modal-confirm')).toBeDisabled();

  // Type 10th char — confirm enabled
  await page.getByTestId('modal-reason-input').fill('1234567890');
  await expect(page.getByTestId('btn-modal-confirm')).toBeEnabled();
});

// ---------------------------------------------------------------------------
// AC-13.5 — Status change 200: modal closes, detail refreshed
// ---------------------------------------------------------------------------

test('AC-13.5: successful status change closes modal and refreshes detail', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'active' });

  let postCallCount = 0;
  await page.route(`**/api/v1/tenants/${TENANT_ID}/status`, async (route) => {
    postCallCount++;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          tenant_id: TENANT_ID,
          previous_status: 'active',
          current_status: 'suspended',
          status_reason: 'Routine maintenance',
          updated_at: '2024-01-02T00:00:00Z',
          updated_by: 'admin@example.com',
        },
      }),
    });
  });

  // Re-mock GET to reflect updated status after modal close
  await page.route(`**/api/v1/tenants/${TENANT_ID}`, (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            ...BASE_TENANT,
            status: 'suspended',
            status_reason: 'Routine maintenance',
          },
        }),
      });
    } else {
      route.continue();
    }
  });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-suspend"]');

  await page.getByTestId('btn-suspend').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  await page.getByTestId('modal-reason-input').fill('Routine maintenance');
  await page.getByTestId('btn-modal-confirm').click();

  // Modal should close
  await expect(page.getByTestId('status-change-modal')).not.toBeVisible({ timeout: 5000 });

  // POST was called
  expect(postCallCount).toBe(1);
});

// ---------------------------------------------------------------------------
// AC-13.6 — Tab key cycles only within modal (focus trap)
// ---------------------------------------------------------------------------

test('AC-13.6: Tab key cycles focus only within modal', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'active' });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-suspend"]');

  await page.getByTestId('btn-suspend').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  // Tab through all focusable elements; after looping back, focus should still be inside modal
  // We verify by checking document.activeElement is within the modal
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press('Tab');
  }

  const isInsideModal = await page.evaluate(() => {
    const modal = document.querySelector('[data-testid="status-change-modal"]');
    return modal?.contains(document.activeElement) ?? false;
  });

  expect(isInsideModal).toBe(true);
});

// ---------------------------------------------------------------------------
// AC-13.7 — Modal close returns focus to triggering button
// ---------------------------------------------------------------------------

test('AC-13.7: closing modal via Cancel restores focus to triggering button', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'active' });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-suspend"]');

  await page.getByTestId('btn-suspend').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  await page.getByTestId('btn-modal-cancel').click();

  // Modal should close
  await expect(page.getByTestId('status-change-modal')).not.toBeVisible({ timeout: 3000 });

  // Focus should be on the Suspend button
  const focusedTestId = await page.evaluate(
    () => (document.activeElement as HTMLElement | null)?.getAttribute('data-testid'),
  );
  expect(focusedTestId).toBe('btn-suspend');
});

// ---------------------------------------------------------------------------
// AC-13.8 — Archive modal: reason field + irreversibility note
// ---------------------------------------------------------------------------

test('AC-13.8: archive modal shows reason field and irreversibility note', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'active' });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-archive"]');

  await page.getByTestId('btn-archive').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  // Reason input present
  await expect(page.getByTestId('modal-reason-input')).toBeVisible();

  // Impact list contains irreversibility language
  await expect(page.getByTestId('modal-impact-list')).toContainText('irreversible');
});

// ---------------------------------------------------------------------------
// AC-13.9 — Activate modal: no reason field shown
// ---------------------------------------------------------------------------

test('AC-13.9: activate modal does not show reason input', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'suspended', status_reason: 'Test suspension' });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-activate"]');

  await page.getByTestId('btn-activate').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  // No reason input
  await expect(page.getByTestId('modal-reason-input')).not.toBeVisible();

  // Confirm is enabled (no reason requirement)
  await expect(page.getByTestId('btn-modal-confirm')).toBeEnabled();
});

// ---------------------------------------------------------------------------
// AC-13.10 — API error on POST /status keeps modal open with inline error
// ---------------------------------------------------------------------------

test('AC-13.10: API error on status change keeps modal open with inline error', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockTenantGet(page, { status: 'active' });

  await page.route(`**/api/v1/tenants/${TENANT_ID}/status`, async (route) => {
    await route.fulfill({
      status: 422,
      contentType: 'application/json',
      body: JSON.stringify({
        error: {
          code: 'forbidden_transition',
          message: 'This transition is not allowed.',
        },
      }),
    });
  });

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await page.waitForSelector('[data-testid="btn-suspend"]');

  await page.getByTestId('btn-suspend').click();
  await page.waitForSelector('[data-testid="status-change-modal"]');

  await page.getByTestId('modal-reason-input').fill('Valid reason text');
  await page.getByTestId('btn-modal-confirm').click();

  // Modal stays open
  await expect(page.getByTestId('status-change-modal')).toBeVisible();

  // Inline error shown
  await expect(page.getByTestId('modal-api-error')).toBeVisible();
  await expect(page.getByTestId('modal-api-error')).toContainText('not allowed');

  // Confirm re-enabled for retry
  await expect(page.getByTestId('btn-modal-confirm')).toBeEnabled();
});
