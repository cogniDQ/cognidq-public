/**
 * Role color identity smoke test.
 *
 * Verifies that after login, the role stripe + badge in the public Layout
 * (`/`) carry the correct `data-role` value matching the user's role. This
 * confirms the per-role color identity works end-to-end through:
 *   backend `/auth/me` → `platform_role` → AuthContext → RoleBadge / RoleStripe.
 *
 * Workspace-specific tests are deliberately omitted here (they depend on the
 * workspace-context cookie + WorkspaceAccessGuard which require a deeper
 * navigation set-up). Run them manually using the credentials below.
 */
import { test, expect, Page } from '@playwright/test';

interface RoleCase {
  email: string;
  password: string;
  /** Expected data-role value rendered by RoleStripe / RoleBadge.
   *  After login, AuthContext prefetches the user's primary workspace_id so
   *  the stripe/badge reflect the effective workspace role even on the public
   *  landing page. Platform operators always show their platform role. */
  homeRole:
    | 'platform_admin'
    | 'tenant_admin'
    | 'workspace_administrator'
    | 'data_engineer'
    | 'data_steward'
    | 'business_analyst'
    | 'governance_viewer'
    | 'unknown';
  badgeText: string;
}

const CASES: RoleCase[] = [
  { email: 'admin@example.com', password: 'admin123',             homeRole: 'platform_admin',          badgeText: 'Platform Administrator' },
  { email: 'qa.tenantadmin@example.com', password: 'change-me-strong-password',   homeRole: 'tenant_admin',            badgeText: 'Tenant Administrator' },
  { email: 'qa.wsadmin@example.com',     password: 'change-me-strong-password',       homeRole: 'workspace_administrator', badgeText: 'Workspace Administrator' },
  { email: 'qa.engineer@example.com',    password: 'change-me-strong-password',      homeRole: 'data_engineer',           badgeText: 'Data Engineer' },
  { email: 'qa.steward@example.com',     password: 'change-me-strong-password',       homeRole: 'data_steward',            badgeText: 'Data Steward' },
  { email: 'qa.member@example.com',      password: 'change-me-strong-password',        homeRole: 'business_analyst',        badgeText: 'Business Analyst' },
  { email: 'qa.viewer@example.com',      password: 'change-me-strong-password',        homeRole: 'governance_viewer',       badgeText: 'Governance Viewer' },
];

async function login(page: Page, email: string, password: string) {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  // Wait until we leave /auth/login (could land on /, /hub, or /admin/...)
  await page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 15_000 });
}

test.describe('Role color identity — Home layout', () => {
  for (const c of CASES) {
    test(`${c.email} renders correct role stripe + badge`, async ({ page }) => {
      await login(page, c.email, c.password);
      // Always navigate to home — Layout is rendered there for everyone.
      await page.goto('/');

      const stripe = page.locator('[data-testid="role-stripe"]');
      await expect(stripe).toBeAttached({ timeout: 10_000 });
      await expect(stripe).toHaveAttribute('data-role', c.homeRole);

      const badge = page.locator('[data-testid="role-badge"]').first();
      await expect(badge).toBeVisible();
      await expect(badge).toContainText(c.badgeText);
    });
  }
});
