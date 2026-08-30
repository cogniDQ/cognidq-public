/**
 * Platform-admin admin-area test.
 *
 * Verifies that after logging in as platform_admin:
 *   1. The admin layout's RoleStripe + RoleBadge use platform_admin theme.
 *   2. The Tenants link is visible in the admin sidebar.
 */
import { test, expect } from '@playwright/test';

test('platform_admin sees red stripe + Platform Administrator badge in /admin/tenants', async ({ page }) => {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill('admin@example.com');
  await page.getByLabel(/password/i).fill('admin123');
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/auth/login'), { timeout: 15_000 });
  await page.goto('/admin/tenants');
  await page.waitForURL(/\/admin\/tenants/, { timeout: 10_000 });

  await expect(page.locator('[data-testid="role-stripe"]')).toHaveAttribute('data-role', 'platform_admin');
  await expect(page.locator('[data-testid="role-badge"]').first()).toContainText('Platform Administrator');
  // Admin layout exposes an Admin link pointing at /admin/tenants
  await expect(page.getByRole('link', { name: 'Admin' })).toHaveAttribute('href', '/admin/tenants');
  // The page itself is the Tenants list
  await expect(page.getByRole('heading', { name: 'Tenants', level: 1 })).toBeVisible();
});
