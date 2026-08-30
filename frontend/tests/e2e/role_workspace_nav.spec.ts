/**
 * Per-role workspace navigation test.
 *
 * For each role, logs in, sets `selected_workspace_id` to the Analytics
 * workspace, and verifies:
 *   1. RoleStripe + RoleBadge in the Hub layout reflect the workspace role.
 *   2. The workspace section of the sidebar contains exactly the items the
 *      role's permissions grant (per FIXED_ROLE_PERMISSIONS).
 *
 * Pre-requisites (already seeded by qa_seed_users.py + manual seed):
 *   qa.wsadmin@example.com    change-me-strong-password     workspace_administrator
 *   qa.engineer@example.com   change-me-strong-password    data_engineer
 *   qa.steward@example.com    change-me-strong-password     data_steward
 *   qa.member@example.com     change-me-strong-password      business_analyst
 *   qa.viewer@example.com     change-me-strong-password      governance_viewer
 */
import { test, expect, Page } from '@playwright/test';

// Seeded Analytics workspace UUID (tenant 1496b2dd-…).
const ANALYTICS_WS_ID = '49d2010f-c5e4-4aa0-9173-bf9cceea5657';

interface NavSpec {
  email: string;
  password: string;
  role: 'workspace_administrator' | 'data_engineer' | 'data_steward' | 'business_analyst' | 'governance_viewer';
  badgeText: string;
  /** Items expected to appear in the sidebar workspace section. */
  visible: string[];
  /** Items expected to be ABSENT from the sidebar. */
  hidden: string[];
}

const ROLES: NavSpec[] = [
  {
    email: 'qa.wsadmin@example.com',
    password: 'change-me-strong-password',
    role: 'workspace_administrator',
    badgeText: 'Workspace Administrator',
    visible: [
      'Overview', 'Data Ingestion', 'Datasets', 'Flows', 'NL Rule Builder',
      'Rules', 'Issues', 'Incidents', 'Alerts', 'Notification Log',
      'Flow Reports', 'Quality Reports', 'Members', 'Roles & Permissions',
      'Workspace Settings', 'Activity Log', 'Permission Audit',
    ],
    hidden: [],
  },
  {
    email: 'qa.engineer@example.com',
    password: 'change-me-strong-password',
    role: 'data_engineer',
    badgeText: 'Data Engineer',
    visible: [
      'Overview', 'Data Ingestion', 'Datasets', 'Flows', 'NL Rule Builder',
      'Rules', 'Issues', 'Incidents', 'Alerts', 'Notification Log',
      'Flow Reports', 'Quality Reports', 'Members',
    ],
    hidden: ['Roles & Permissions', 'Workspace Settings', 'Activity Log', 'Permission Audit'],
  },
  {
    email: 'qa.steward@example.com',
    password: 'change-me-strong-password',
    role: 'data_steward',
    badgeText: 'Data Steward',
    visible: [
      'Overview', 'Datasets', 'Flows', 'NL Rule Builder', 'Rules', 'Issues',
      'Incidents', 'Alerts', 'Notification Log', 'Flow Reports', 'Quality Reports', 'Members',
    ],
    hidden: ['Data Ingestion', 'Roles & Permissions', 'Workspace Settings', 'Activity Log', 'Permission Audit'],
  },
  {
    email: 'qa.member@example.com',
    password: 'change-me-strong-password',
    role: 'business_analyst',
    badgeText: 'Business Analyst',
    visible: [
      'Overview', 'Datasets', 'Flows', 'Rules', 'Issues', 'Incidents',
      'Flow Reports', 'Quality Reports', 'Members',
    ],
    hidden: [
      'Data Ingestion', 'NL Rule Builder', 'Alerts', 'Notification Log',
      'Roles & Permissions', 'Workspace Settings', 'Activity Log', 'Permission Audit',
    ],
  },
  {
    email: 'qa.viewer@example.com',
    password: 'change-me-strong-password',
    role: 'governance_viewer',
    badgeText: 'Governance Viewer',
    visible: [
      'Overview', 'Datasets', 'Flows', 'Rules', 'Issues', 'Incidents',
      'Flow Reports', 'Quality Reports', 'Members',
    ],
    hidden: [
      'Data Ingestion', 'NL Rule Builder', 'Alerts', 'Notification Log',
      'Roles & Permissions', 'Workspace Settings', 'Activity Log', 'Permission Audit',
    ],
  },
];

async function loginAndOpenWorkspace(page: Page, email: string, password: string) {
  // Pre-set the selected workspace so WorkspaceContext picks Analytics
  // immediately on first render (avoids the auto-select-first race).
  await page.addInitScript(([wsId]) => {
    localStorage.setItem('selected_workspace_id', wsId as string);
  }, [ANALYTICS_WS_ID]);

  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/auth/login'), { timeout: 15_000 });

  // Go directly to the Analytics workspace overview page.
  await page.goto(`/hub/ws/${ANALYTICS_WS_ID}/overview`);
  // Wait until the role stripe carries the *expected* role (i.e. workspace
  // role has been resolved — not the initial "unknown").
  await page.locator('[data-testid="role-stripe"]').waitFor({ state: 'attached', timeout: 10_000 });
}

test.describe('Per-role workspace UI: stripe, badge & nav visibility (Analytics WS)', () => {
  for (const spec of ROLES) {
    test(`${spec.role}: badge "${spec.badgeText}" + sidebar matches permissions`, async ({ page }) => {
      await loginAndOpenWorkspace(page, spec.email, spec.password);

      // Wait for the workspace role to be resolved by useWorkspacePermissions.
      await expect(page.locator('[data-testid="role-stripe"]')).toHaveAttribute(
        'data-role',
        spec.role,
        { timeout: 10_000 },
      );
      await expect(page.locator('[data-testid="role-badge"]').first()).toContainText(spec.badgeText);

      // The sidebar uses <Link> elements rendered by react-router; assert
      // exact-match link text within the sidebar nav.
      const sidebar = page.locator('nav').first();
      for (const label of spec.visible) {
        await expect(
          sidebar.getByRole('link', { name: new RegExp(`^${label}$`) }),
          `Expected nav item "${label}" to be visible for ${spec.role}`,
        ).toBeVisible();
      }
      for (const label of spec.hidden) {
        await expect(
          sidebar.getByRole('link', { name: new RegExp(`^${label}$`) }),
          `Expected nav item "${label}" to be HIDDEN for ${spec.role}`,
        ).toHaveCount(0);
      }
    });
  }
});
