/**
 * F001 – Packet 12: Tenant Detail Page
 *
 * E2E tests verify:
 *   AC-12.1  Draft tenant: ActivateButton absent, SuspendButton absent, ArchiveButton present
 *   AC-12.2  Active tenant: SuspendButton and ArchiveButton present; ActivateButton absent
 *   AC-12.3  Archived tenant: no action buttons; EditMetadataButton absent; actions panel shows "No actions available"
 *   AC-12.4  workspace_count_available = false → "Count unavailable" shown, not 0
 *   AC-12.5  Platform Viewer: all 5 sections visible; TenantActionsPanel absent
 *   AC-12.6  Unknown tenant_id → not-found state rendered
 *
 * Additional coverage:
 *   AC-12.7  Platform Admin views all 5 sections with correct field data
 *   AC-12.8  Suspended tenant: ActivateButton and ArchiveButton present; SuspendButton absent
 *   AC-12.9  AuditSummaryLink always rendered
 *
 * ── Mocking strategy ──────────────────────────────────────────────────────
 * - Auth faked via addInitScript + localStorage (same pattern as Packet 10/11).
 * - GET /api/v1/tenants/:id intercepted via page.route().
 * - Fixture data covers all four statuses and the unavailable counts scenario.
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

const TENANT_ID = 'tid-detail-001';

function buildTenantFixture(
  overrides: Partial<{
    status: string;
    status_reason: string | null;
    workspace_count_available: boolean;
    user_count_available: boolean;
  }> = {},
) {
  return {
    data: {
      tenant_id: TENANT_ID,
      tenant_name: 'Acme Corp',
      tenant_slug: 'acme-corp',
      status: overrides.status ?? 'active',
      status_reason: overrides.status_reason ?? null,
      region: 'eu-west',
      plan: 'growth',
      service_start_date: '2024-01-15',
      tenant_notes: 'Test notes for Acme Corp.',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-03-20T08:30:00Z',
      created_by: 'creator-id',
      updated_by: 'updater-id',
      workspace_count: 3,
      workspace_count_available: overrides.workspace_count_available ?? true,
      user_count: 12,
      user_count_available: overrides.user_count_available ?? true,
      audit_summary_link: `/api/v1/tenants/${TENANT_ID}/audit-logs`,
    },
  };
}

async function mockDetailApi(page: Page, fixture: object): Promise<void> {
  await page.route(`**/api/v1/tenants/${TENANT_ID}`, (route: Route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixture),
      });
    } else {
      route.continue();
    }
  });
}

async function mock404(page: Page): Promise<void> {
  await page.route(`**/api/v1/tenants/${TENANT_ID}`, (route: Route) => {
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: { code: 'not_found', message: 'Not found.', fields: null } }),
    });
  });
}

// ---------------------------------------------------------------------------
// AC-12.7  Platform Admin sees all 5 sections with correct data
// ---------------------------------------------------------------------------

test('AC-12.7: Platform Admin sees all five sections with correct field data', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(page, buildTenantFixture({ status: 'active' }));

  await page.goto(`/admin/tenants/${TENANT_ID}`);

  // All five sections present
  await expect(page.getByTestId('section-identity')).toBeVisible();
  await expect(page.getByTestId('section-lifecycle')).toBeVisible();
  await expect(page.getByTestId('section-operational')).toBeVisible();
  await expect(page.getByTestId('section-counts')).toBeVisible();
  await expect(page.getByTestId('audit-summary-link')).toBeVisible();

  // Spot-check data
  await expect(page.getByTestId('detail-tenant-name')).toHaveText('Acme Corp');
  await expect(page.getByTestId('detail-tenant-slug')).toHaveText('acme-corp');
  await expect(page.getByTestId('detail-plan')).toContainText('Growth');
  await expect(page.getByTestId('detail-region')).toContainText('EU West');
  await expect(page.getByTestId('detail-workspace-count')).toHaveText('3');
  await expect(page.getByTestId('detail-user-count')).toHaveText('12');
});

// ---------------------------------------------------------------------------
// AC-12.1  Draft tenant button visibility
// ---------------------------------------------------------------------------

test('AC-12.1: draft tenant — ActivateButton and SuspendButton absent; ArchiveButton present', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(page, buildTenantFixture({ status: 'draft' }));

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await expect(page.getByTestId('tenant-actions-panel')).toBeVisible();

  await expect(page.getByTestId('btn-activate')).not.toBeAttached();
  await expect(page.getByTestId('btn-suspend')).not.toBeAttached();
  await expect(page.getByTestId('btn-archive')).toBeVisible();
  await expect(page.getByTestId('btn-edit-metadata')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-12.2  Active tenant button visibility
// ---------------------------------------------------------------------------

test('AC-12.2: active tenant — SuspendButton and ArchiveButton present; ActivateButton absent', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(page, buildTenantFixture({ status: 'active' }));

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await expect(page.getByTestId('tenant-actions-panel')).toBeVisible();

  await expect(page.getByTestId('btn-activate')).not.toBeAttached();
  await expect(page.getByTestId('btn-suspend')).toBeVisible();
  await expect(page.getByTestId('btn-archive')).toBeVisible();
  await expect(page.getByTestId('btn-edit-metadata')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-12.8  Suspended tenant button visibility
// ---------------------------------------------------------------------------

test('AC-12.8: suspended tenant — ActivateButton and ArchiveButton present; SuspendButton absent', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(
    page,
    buildTenantFixture({ status: 'suspended', status_reason: 'Maintenance window.' }),
  );

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await expect(page.getByTestId('tenant-actions-panel')).toBeVisible();

  await expect(page.getByTestId('btn-activate')).toBeVisible();
  await expect(page.getByTestId('btn-suspend')).not.toBeAttached();
  await expect(page.getByTestId('btn-archive')).toBeVisible();
  await expect(page.getByTestId('btn-edit-metadata')).toBeVisible();

  // Status reason should be visible
  await expect(page.getByTestId('detail-status-reason')).toContainText('Maintenance window.');
});

// ---------------------------------------------------------------------------
// AC-12.3  Archived tenant — no buttons, no edit
// ---------------------------------------------------------------------------

test('AC-12.3: archived tenant — no action buttons; EditMetadataButton absent', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(
    page,
    buildTenantFixture({ status: 'archived', status_reason: 'Decommissioned.' }),
  );

  await page.goto(`/admin/tenants/${TENANT_ID}`);
  await expect(page.getByTestId('tenant-actions-panel')).toBeVisible();

  await expect(page.getByTestId('btn-activate')).not.toBeAttached();
  await expect(page.getByTestId('btn-suspend')).not.toBeAttached();
  await expect(page.getByTestId('btn-archive')).not.toBeAttached();
  await expect(page.getByTestId('btn-edit-metadata')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-12.4  workspace_count_available = false → unavailability indicator
// ---------------------------------------------------------------------------

test('AC-12.4: workspace_count_available=false shows unavailability indicator, not 0', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(
    page,
    buildTenantFixture({ workspace_count_available: false }),
  );

  await page.goto(`/admin/tenants/${TENANT_ID}`);

  // The numeric count element must NOT be visible
  await expect(page.getByTestId('detail-workspace-count')).not.toBeAttached();

  // The "count unavailable" indicator must be visible
  await expect(page.getByTestId('workspace-count-unavailable')).toBeVisible();
  await expect(page.getByTestId('workspace-count-unavailable')).toContainText('unavailable');

  // User count should still show normally
  await expect(page.getByTestId('detail-user-count')).toBeVisible();
});

// ---------------------------------------------------------------------------
// AC-12.5  Platform Viewer — all 5 sections visible; actions panel absent
// ---------------------------------------------------------------------------

test('AC-12.5: Platform Viewer sees all 5 sections but no TenantActionsPanel', async ({
  page,
}) => {
  await setupAuth(page, 'platform_viewer');
  await mockDetailApi(page, buildTenantFixture({ status: 'active' }));

  await page.goto(`/admin/tenants/${TENANT_ID}`);

  // All five sections visible
  await expect(page.getByTestId('section-identity')).toBeVisible();
  await expect(page.getByTestId('section-lifecycle')).toBeVisible();
  await expect(page.getByTestId('section-operational')).toBeVisible();
  await expect(page.getByTestId('section-counts')).toBeVisible();
  await expect(page.getByTestId('audit-summary-link')).toBeVisible();

  // Actions panel must be entirely absent
  await expect(page.getByTestId('tenant-actions-panel')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-12.6  Unknown tenant_id → not-found state
// ---------------------------------------------------------------------------

test('AC-12.6: unknown tenant_id renders the not-found state', async ({ page }) => {
  await setupAuth(page, 'platform_admin');
  await mock404(page);

  await page.goto(`/admin/tenants/${TENANT_ID}`);

  await expect(page.getByTestId('detail-not-found')).toBeVisible();
  // Content section should NOT be rendered
  await expect(page.getByTestId('tenant-detail-page')).not.toBeAttached();
});

// ---------------------------------------------------------------------------
// AC-12.9  AuditSummaryLink always rendered (for both roles)
// ---------------------------------------------------------------------------

test('AC-12.9: audit summary link is always present and navigates to audit-logs route', async ({
  page,
}) => {
  await setupAuth(page, 'platform_admin');
  await mockDetailApi(page, buildTenantFixture({ status: 'active' }));

  await page.goto(`/admin/tenants/${TENANT_ID}`);

  const link = page.getByTestId('audit-summary-link');
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute('href', `/admin/tenants/${TENANT_ID}/audit-logs`);
});
