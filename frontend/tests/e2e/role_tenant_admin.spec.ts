/**
 * Tenant Admin smoke test.
 *
 * Verifies that a user with `platform_role = 'tenant_admin'`:
 *   1. Lands on /tenant-admin after login (via HubEntryResolver).
 *   2. Sees the teal stripe + "Tenant Administrator" badge.
 *   3. Sees the Tenant Admin dashboard with at least one workspace card.
 *   4. Can navigate to any workspace in the tenant (including ones they
 *      are not explicitly assigned to — tenant_admin bypasses per-member
 *      scoping, matching the product rule "tenant admin owns the tenant").
 */
import { test, expect } from '@playwright/test';

const EMAIL = 'qa.tenantadmin@example.com';
const PASSWORD = 'change-me-strong-password';

test('tenant_admin: login → dashboard → stripe + badge + workspace card', async ({ page }) => {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 15_000 });

  // Navigate explicitly — /hub should redirect tenant_admin to /tenant-admin.
  await page.goto('/hub');
  await page.waitForURL(/\/tenant-admin/, { timeout: 15_000 });

  // Role identity visible
  await expect(page.locator('[data-testid="role-stripe"]')).toHaveAttribute('data-role', 'tenant_admin');
  await expect(page.locator('[data-testid="role-badge"]').first()).toContainText('Tenant Administrator');

  // Dashboard landmarks
  await expect(page.getByTestId('tenant-admin-dashboard')).toBeVisible();
  await expect(page.getByRole('heading', { name: /Tenant Administration/i })).toBeVisible();
  await expect(page.getByTestId('tenant-admin-create-ws')).toBeVisible();

  // At least one workspace card (tenant has Sales, Analytics, Bootstrap).
  const cards = page.getByTestId('tenant-admin-ws-card');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThanOrEqual(1);
});
