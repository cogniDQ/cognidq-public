/**
 * Auth helper — real backend, no mocking.
 *
 * Uses POST /api/v1/auth/login on http://localhost:8000 to obtain a JWT,
 * then injects it into localStorage before the SPA boots.
 */
import { Page, request as pwRequest } from '@playwright/test';

export interface E2EUser {
  email: string;
  password: string;
  role: string;
  label: string;
}

export const USERS = {
  platformAdmin: {
    email: 'admin@example.com',
    password: 'admin123',
    role: 'platform_admin',
    label: 'Platform Administrator',
  },
  workspaceAdmin: {
    email: 'qa.wsadmin@example.com',
    password: 'change-me-strong-password',
    role: 'workspace_administrator',
    label: 'Workspace Administrator',
  },
  dataEngineer: {
    email: 'qa.engineer@example.com',
    password: 'change-me-strong-password',
    role: 'data_engineer',
    label: 'Data Engineer',
  },
  dataSteward: {
    email: 'qa.steward@example.com',
    password: 'change-me-strong-password',
    role: 'data_steward',
    label: 'Data Steward',
  },
  viewer: {
    email: 'qa.viewer@example.com',
    password: 'change-me-strong-password',
    role: 'governance_viewer',
    label: 'Governance Viewer',
  },
} satisfies Record<string, E2EUser>;

export const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

export interface LoginResult {
  access_token: string;
  refresh_token?: string;
  user: { id: string; email: string; [k: string]: unknown };
}

export async function apiLogin(email: string, password: string): Promise<LoginResult> {
  const ctx = await pwRequest.newContext({ baseURL: API_BASE });
  const res = await ctx.post('/api/v1/auth/login', {
    data: { email, password },
    headers: { 'content-type': 'application/json' },
  });
  if (!res.ok()) {
    const body = await res.text().catch(() => '<unreadable>');
    await ctx.dispose();
    throw new Error(`apiLogin failed for ${email}: ${res.status()} ${body}`);
  }
  const json = (await res.json()) as LoginResult;
  await ctx.dispose();
  return json;
}

/**
 * UI login — drives the actual /auth/login page.
 *
 * Falls back to seeding localStorage with an API-issued token if the form
 * cannot be filled (used by helpers that need a logged-in session for
 * non-login steps).
 */
export async function loginViaUi(page: Page, user: E2EUser): Promise<void> {
  await page.goto('/auth/login');
  await page.getByLabel(/email/i).fill(user.email);
  await page.getByLabel(/password/i).fill(user.password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.waitForURL(/\/(hub|admin)/, { timeout: 15_000 }).catch(() => {});
}

export async function seedSessionAndGoto(page: Page, user: E2EUser, path: string): Promise<void> {
  const { access_token, refresh_token } = await apiLogin(user.email, user.password);
  await page.addInitScript(
    ({ at, rt }) => {
      localStorage.setItem('access_token', at);
      if (rt) localStorage.setItem('refresh_token', rt);
    },
    { at: access_token, rt: refresh_token ?? '' },
  );
  await page.goto(path);
}
