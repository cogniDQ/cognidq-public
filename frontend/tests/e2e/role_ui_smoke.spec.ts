/**
 * Role-based UI smoke test.
 *
 * Logs in via the real backend as each test user and verifies:
 *   1. The role stripe (`[data-testid="role-stripe"]`) shows the expected role.
 *   2. The role badge text matches.
 *   3. The visible navigation items match what the role is allowed to see.
 *
 * Pre-conditions (already seeded):
 *   - admin@example.com / admin123          → platform_admin
 *   - qa.wsadmin@example.com    / change-me-strong-password     → workspace_administrator (Analytics)
 *   - qa.engineer@example.com   / change-me-strong-password    → data_engineer            (Analytics)
 *   - qa.steward@example.com    / change-me-strong-password     → data_steward             (Analytics)
 *   - qa.member@example.com     / change-me-strong-password      → business_analyst         (Analytics)
 *   - qa.viewer@example.com     / change-me-strong-password      → governance_viewer        (Analytics)
 */
import { test, expect, Page } from '@playwright/test';

interface RoleCase {
  email: string;
  password: string;
  role: string;
  badgeLabel: string;
  /** nav items expected to be visible in the workspace section */
  expectVisible: string[];
  /** nav items expected to be HIDDEN in the workspace section */
  expectHidden: string[];
}

const CASES: RoleCase[] = [
  {
    email: 'qa.wsadmin@example.com',
    password: 'change-me-strong-password',
    role: 'workspace_administrator',
    badgeLabel: 'Workspace Administrator',
    expectVisible: ['Overview', 'Datasets', 'Rules', 'Members', 'Roles & Permissions', 'Workspace Settings', 'Activity Log'],
    expectHidden: [],
  },
  {
    email: 'qa.engineer@example.com',
    password: 'change-me-strong-password',
    role: 'data_engineer',
    badgeLabel: 'Data Engineer',
    expectVisible: ['Overview', 'Data Ingestion', 'Datasets', 'Rules', 'NL Rule Builder', 'Flows'],
    expectHidden: ['Roles & Permissions', 'Workspace Settings', 'Activity Log', 'Permission Audit'],
  },
  {
    email: 'qa.steward@example.com',
    password: 'change-me-strong-password',
    role: 'data_steward',
    badgeLabel: 'Data Steward',
    expectVisible: ['Overview', 'Datasets', 'Rules', 'NL Rule Builder', 'Issues'],
    expectHidden: ['Data Ingestion', 'Roles & Permissions', 'Workspace Settings', 'Activity Log'],
  },
  {
    email: 'qa.member@example.com',
    password: 'change-me-strong-password',
    role: 'business_analyst',
    badgeLabel: 'Business Analyst',
    expectVisible: ['Overview', 'Datasets', 'Rules', 'Issues', 'Quality Reports'],
    expectHidden: ['Data Ingestion', 'NL Rule Builder', 'Roles & Permissions', 'Workspace Settings'],
  },
  {
    email: 'qa.viewer@example.com',
    password: 'change-me-strong-password',
    role: 'governance_viewer',
    badgeLabel: 'Governance Viewer',
    expectVisible: ['Overview', 'Datasets', 'Rules', 'Issues'],
    expectHidden: ['Data Ingestion', 'NL Rule Builder', 'Roles & Permissions', 'Workspace Settings', 'Activity Log'],
  },
];

async function loginAndOpenHub(page: Page, email: string, password: string) {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  // Wait for either redirect to / or to /hub
  await page.waitForURL(/\/(hub|admin|$|home)/, { timeout: 15_000 }).catch(() => {});
}

test.describe('Role-based UI: stripe, badge, and nav visibility', () => {
  test('platform_admin sees red stripe + Platform section + Tenants', async ({ page }) => {
    await loginAndOpenHub(page, 'admin@example.com', 'admin123');
    // Platform admin lands on /admin/tenants (AdminRedirect)
    await page.waitForURL(/\/admin\/tenants/, { timeout: 15_000 });
    const stripe = page.getByTestId('role-stripe');
    await expect(stripe).toHaveAttribute('data-role', 'platform_admin');
    await expect(page.getByTestId('role-badge')).toContainText('Platform Administrator');
  });

  for (const c of CASES) {
    test(`${c.role}: badge "${c.badgeLabel}" + correct nav items visible`, async ({ page }) => {
      await loginAndOpenHub(page, c.email, c.password);
      // Navigate into the Hub workspace area for the Analytics workspace
      await page.goto('/hub/workspaces');
      // Click Analytics workspace
      await page.getByRole('link', { name: /Analytics/ }).first().click({ timeout: 10_000 }).catch(() => {});
      // Wait for hub layout to show role badge
      await page.waitForSelector('[data-testid="role-stripe"]', { timeout: 10_000 });
      const stripe = page.getByTestId('role-stripe');
      await expect(stripe).toHaveAttribute('data-role', c.role);
      await expect(page.getByTestId('role-badge').first()).toContainText(c.badgeLabel);

      // Verify nav items
      for (const item of c.expectVisible) {
        await expect(page.getByRole('link', { name: new RegExp(`^${item}$`) }).first()).toBeVisible();
      }
      for (const item of c.expectHidden) {
        await expect(page.getByRole('link', { name: new RegExp(`^${item}$`) })).toHaveCount(0);
      }
    });
  }
});
