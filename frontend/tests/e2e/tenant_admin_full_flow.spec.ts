/**
 * Tenant admin UI walkthrough — verifies the end-to-end flow requested by the
 * user: "members adding should be tenant level and members assignement to
 * workspace should be workspace level".
 *
 * Steps:
 *   1. Log in as qa.tenantadmin → HubEntryResolver redirects to /tenant-admin.
 *   2. Dashboard lists tenant workspaces.
 *   3. Navigate to /tenant-admin/members → create a new invitation
 *      (tenant-level add), assert the acceptance URL is displayed once.
 *   4. Open a workspace and verify that the tenant admin can access the
 *      workspace Members page (workspace-level role management surface).
 */
import { test, expect } from '@playwright/test';

const EMAIL = 'qa.tenantadmin@example.com';
const PASSWORD = 'change-me-strong-password';

async function login(page: import('@playwright/test').Page, email: string, password: string) {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 15_000 });
}

test('tenant_admin: full UI walkthrough (dashboard → invite → workspace members)', async ({ page }) => {
  await login(page, EMAIL, PASSWORD);

  // Land on / and navigate to /hub so HubEntryResolver runs.
  await page.goto('/hub');
  await page.waitForURL(/\/tenant-admin(?:\/|$)/, { timeout: 15_000 });

  // Dashboard
  await expect(page.getByTestId('tenant-admin-dashboard')).toBeVisible();
  const cards = page.getByTestId('tenant-admin-ws-card');
  await expect(cards.first()).toBeVisible();
  const cardCount = await cards.count();
  expect(cardCount).toBeGreaterThanOrEqual(1);

  // Go to tenant members page
  await page.getByTestId('tenant-admin-manage-members').click();
  await page.waitForURL(/\/tenant-admin\/members/);
  await expect(page.getByTestId('tenant-members-page')).toBeVisible();

  // Create an invitation
  await page.getByTestId('tenant-members-invite-btn').click();
  const uniqueEmail = `qa.invitee+${Date.now()}@example.com`;
  await page.getByTestId('invite-email-input').fill(uniqueEmail);
  await page.getByTestId('invite-role-select').selectOption('data_steward');
  await page.getByTestId('invite-submit-btn').click();

  // Acceptance URL must be shown once.
  const urlArea = page.getByTestId('invitation-url');
  await expect(urlArea).toBeVisible({ timeout: 10_000 });
  const urlValue = await urlArea.inputValue();
  expect(urlValue).toMatch(/accept-invitation\?token=/);

  await page.getByRole('button', { name: /^done$/i }).click();

  // Invitation should now appear in the pending list. Reload to avoid any
  // race between the modal close handler and the list refresh.
  await page.reload();
  await expect(page.getByTestId('tenant-invitations-table')).toBeVisible();
  await expect(
    page.getByTestId('tenant-invitations-table').locator('tr', { hasText: uniqueEmail })
  ).toBeVisible({ timeout: 10_000 });

  // Back to dashboard, then open a workspace and reach its Members page.
  await page.goto('/tenant-admin');
  const firstCard = page.getByTestId('tenant-admin-ws-card').first();
  await firstCard.getByRole('button', { name: /members/i }).click();
  await page.waitForURL(/\/hub\/ws\/[0-9a-f-]+\/members/);
  await expect(page.getByRole('heading', { name: /workspace members/i })).toBeVisible();
  // As tenant_admin, we must see the Add Member control (canEdit=true).
  await expect(page.getByRole('button', { name: /add member/i })).toBeVisible();
});
