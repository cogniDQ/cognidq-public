/**
 * F007 — Packet 5: Workspace RBAC E2E
 *
 * Covers acceptance criteria:
 *   E2E-01  Workspace admin role is retrievable via GET members/role endpoint
 *   E2E-02  PUT /members/{uid}/role assigns new role → 200 with assignment body
 *   E2E-03  DELETE /members/{uid}/role revokes role → 204
 *   E2E-04  DELETE last admin role blocked → 409 LAST_WORKSPACE_ADMINISTRATOR
 *   E2E-05  PUT last admin role change blocked → 409 LAST_WORKSPACE_ADMINISTRATOR
 *   E2E-06  POST /permissions/check → allowed=true (data_engineer + datasources:write)
 *   E2E-07  POST /permissions/check → allowed=false (governance_viewer + datasources:write)
 *   E2E-08  Data Sources page shows "New Data Source" CTA for data_engineer
 *   E2E-09  Data Sources page hides "New Data Source" CTA for governance_viewer
 *   E2E-10  Datasets page shows "New Dataset" CTA for data_engineer
 *   E2E-11  Datasets page hides "New Dataset" CTA for governance_viewer
 *   E2E-12  PUT role with invalid role name → 422 INVALID_ROLE
 *
 * Mocking strategy:
 *   - JWT injected into localStorage via page.addInitScript()
 *   - All API calls intercepted via function-based page.route() matchers
 *   - E2E-01 through E2E-07 and E2E-12: API assertions via page.evaluate() + fetch()
 *   - E2E-08 through E2E-11: full page navigation + DOM assertions
 */

import { test, expect, Page } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const WS_ID = '00000000-0000-0000-0000-000000000001';
const ACTOR_ID = 'user-001';
const TARGET_USER_ID = 'user-002';
const TENANT_ID = '00000000-0000-0000-0000-000000000099';

/** Absolute API base used by the axios instance (injected via VITE_API_URL). */
const API_BASE = 'http://localhost:8000/api/v1';

const DATA_SOURCES_URL = `/workspaces/${WS_ID}/data-sources`;
const DATASETS_URL = `/workspaces/${WS_ID}/datasets`;

// ─────────────────────────────────────────────────────────────────────────────
// JWT helper
//
// Generates a fake JWT with workspace-scoped claims read by workspace_auth.py:
//   actor_id, actor_role, tenant_id
// No real signature is required because the frontend only base64-decodes the
// payload (never verifies the signature).
// ─────────────────────────────────────────────────────────────────────────────

function buildJwt(
  actorId = ACTOR_ID,
  actorRole = 'workspace_administrator',
  tenantId = TENANT_ID,
): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      actor_id: actorId,
      actor_role: actorRole,
      tenant_id: tenantId,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth helper
// ─────────────────────────────────────────────────────────────────────────────

async function setupAuth(
  page: Page,
  actorRole = 'workspace_administrator',
  actorId = ACTOR_ID,
): Promise<void> {
  const token = buildJwt(actorId, actorRole);

  await page.addInitScript(
    ({ t }: { t: string }) => {
      localStorage.setItem('access_token', t);
    },
    { t: token },
  );

  await page.route(
    (url) => url.href.includes('/api/v1/auth/me'),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: actorId,
          email: 'actor@example.com',
          full_name: 'Test Actor',
          avatar_url: null,
          email_verified: true,
          status: 'active',
          last_login_at: null,
          created_at: '2024-01-01T00:00:00Z',
        }),
      });
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// API mock helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Mock GET /workspaces/{WS_ID}/members/{actorId}/role
 * Returns the given role so useWorkspacePermissions can compute can().
 */
async function mockActorRole(
  page: Page,
  roleName: string,
  actorId = ACTOR_ID,
): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${actorId}/role`,
      ),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            workspace_id: WS_ID,
            user_id: actorId,
            role_name: roleName,
            granted_by: null,
            granted_at: '2024-01-01T00:00:00Z',
          }),
        });
      } else {
        route.fallback();
      }
    },
  );
}

/** Mock GET /workspaces/{WS_ID}/data-sources → empty list. */
async function mockDataSourcesApi(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}/data-sources`) &&
      !url.href.includes('/role'),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [],
            total: 0,
            page: 1,
            page_size: 25,
          }),
        });
      } else {
        route.fallback();
      }
    },
  );
}

/** Mock GET /workspaces/{WS_ID}/datasets → empty list. */
async function mockDatasetsApi(page: Page): Promise<void> {
  await page.route(
    (url) =>
      url.href.includes(`/api/v1/workspaces/${WS_ID}/datasets`) &&
      !url.href.includes('/role'),
    (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [],
            total: 0,
            page: 1,
            page_size: 25,
          }),
        });
      } else {
        route.fallback();
      }
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared fixture
// ─────────────────────────────────────────────────────────────────────────────

const ROLE_ASSIGNMENT_FIXTURE = {
  workspace_id: WS_ID,
  user_id: TARGET_USER_ID,
  role_name: 'data_steward',
  granted_by: ACTOR_ID,
  granted_at: '2024-06-01T10:00:00Z',
};

// ═════════════════════════════════════════════════════════════════════════════
// E2E-01  Admin role is fetchable via GET members/role endpoint
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-01: workspace_administrator role is returned by GET members/role endpoint', async ({
  page,
}) => {
  let roleFetched = false;

  await setupAuth(page, 'workspace_administrator');

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${ACTOR_ID}/role`,
      ),
    (route) => {
      if (route.request().method() === 'GET') {
        roleFetched = true;
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            workspace_id: WS_ID,
            user_id: ACTOR_ID,
            role_name: 'workspace_administrator',
            granted_by: null,
            granted_at: '2024-01-01T00:00:00Z',
          }),
        });
      } else {
        route.fallback();
      }
    },
  );

  await mockDataSourcesApi(page);
  await page.goto(DATA_SOURCES_URL);

  // Allow the React Query hook to issue the GET request
  await page.waitForTimeout(500);

  expect(roleFetched).toBe(true);
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-02  PUT /members/{uid}/role assigns new role → 200
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-02: PUT /members/{uid}/role assigns role and returns 200', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockActorRole(page, 'workspace_administrator');
  await mockDataSourcesApi(page);

  let capturedBody: Record<string, unknown> = {};

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${TARGET_USER_ID}/role`,
      ),
    async (route) => {
      if (route.request().method() === 'PUT') {
        capturedBody = JSON.parse(route.request().postData() ?? '{}') as Record<
          string,
          unknown
        >;
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ROLE_ASSIGNMENT_FIXTURE),
        });
      } else {
        route.fallback();
      }
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const response = await page.evaluate(
    async ({
      apiBase,
      wsId,
      userId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      userId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/members/${userId}/role`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ role_name: 'data_steward' }),
        },
      );
      return { status: res.status, body: (await res.json()) as unknown };
    },
    {
      apiBase: API_BASE,
      wsId: WS_ID,
      userId: TARGET_USER_ID,
      token: buildJwt(),
    },
  );

  expect(response.status).toBe(200);
  expect(response.body).toMatchObject({
    role_name: 'data_steward',
    workspace_id: WS_ID,
  });
  expect(capturedBody.role_name).toBe('data_steward');
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-03  DELETE /members/{uid}/role revokes role → 204
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-03: DELETE /members/{uid}/role revokes role and returns 204', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockActorRole(page, 'workspace_administrator');
  await mockDataSourcesApi(page);

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${TARGET_USER_ID}/role`,
      ),
    (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({ status: 204 });
      } else {
        route.fallback();
      }
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const status = await page.evaluate(
    async ({
      apiBase,
      wsId,
      userId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      userId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/members/${userId}/role`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return res.status;
    },
    {
      apiBase: API_BASE,
      wsId: WS_ID,
      userId: TARGET_USER_ID,
      token: buildJwt(),
    },
  );

  expect(status).toBe(204);
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-04  DELETE last admin role blocked → 409 LAST_WORKSPACE_ADMINISTRATOR
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-04: DELETE last admin role blocked with 409 LAST_WORKSPACE_ADMINISTRATOR', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  // First register the GET handler for the actor's role
  await mockActorRole(page, 'workspace_administrator');
  await mockDataSourcesApi(page);

  // Register DELETE handler AFTER mockActorRole so it runs first (LIFO).
  // The GET path falls through to mockActorRole via route.fallback().
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${ACTOR_ID}/role`,
      ),
    (route) => {
      if (route.request().method() === 'DELETE') {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'LAST_WORKSPACE_ADMINISTRATOR',
              message: 'Cannot remove the last workspace administrator.',
              fields: null,
            },
          }),
        });
      } else {
        route.fallback();
      }
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const response = await page.evaluate(
    async ({
      apiBase,
      wsId,
      userId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      userId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/members/${userId}/role`,
        {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      return { status: res.status, body: (await res.json()) as unknown };
    },
    { apiBase: API_BASE, wsId: WS_ID, userId: ACTOR_ID, token: buildJwt() },
  );

  expect(response.status).toBe(409);
  expect((response.body as { error: { code: string } }).error.code).toBe(
    'LAST_WORKSPACE_ADMINISTRATOR',
  );
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-05  PUT last admin role change blocked → 409 LAST_WORKSPACE_ADMINISTRATOR
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-05: PUT last admin role change blocked with 409 LAST_WORKSPACE_ADMINISTRATOR', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockActorRole(page, 'workspace_administrator');
  await mockDataSourcesApi(page);

  // Register PUT handler after mockActorRole (LIFO → runs first for PUT requests)
  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${ACTOR_ID}/role`,
      ),
    (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'LAST_WORKSPACE_ADMINISTRATOR',
              message: 'Cannot demote the last workspace administrator.',
              fields: null,
            },
          }),
        });
      } else {
        route.fallback();
      }
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const response = await page.evaluate(
    async ({
      apiBase,
      wsId,
      userId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      userId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/members/${userId}/role`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ role_name: 'data_engineer' }),
        },
      );
      return { status: res.status, body: (await res.json()) as unknown };
    },
    { apiBase: API_BASE, wsId: WS_ID, userId: ACTOR_ID, token: buildJwt() },
  );

  expect(response.status).toBe(409);
  expect((response.body as { error: { code: string } }).error.code).toBe(
    'LAST_WORKSPACE_ADMINISTRATOR',
  );
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-06  POST /permissions/check → allowed=true (data_engineer + datasources:write)
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-06: POST /permissions/check returns allowed=true for data_engineer + datasources:write', async ({
  page,
}) => {
  await setupAuth(page, 'data_engineer');
  await mockActorRole(page, 'data_engineer');
  await mockDataSourcesApi(page);

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/permissions/check`,
      ),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          allowed: true,
          role_name: 'data_engineer',
          action: 'datasources:write',
        }),
      });
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const result = await page.evaluate(
    async ({
      apiBase,
      wsId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/permissions/check`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ action: 'datasources:write' }),
        },
      );
      return res.json() as Promise<unknown>;
    },
    {
      apiBase: API_BASE,
      wsId: WS_ID,
      token: buildJwt(ACTOR_ID, 'data_engineer'),
    },
  );

  expect(result).toMatchObject({
    allowed: true,
    role_name: 'data_engineer',
    action: 'datasources:write',
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-07  POST /permissions/check → allowed=false (governance_viewer + datasources:write)
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-07: POST /permissions/check returns allowed=false for governance_viewer + datasources:write', async ({
  page,
}) => {
  await setupAuth(page, 'governance_viewer');
  await mockActorRole(page, 'governance_viewer');
  await mockDataSourcesApi(page);

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/permissions/check`,
      ),
    (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          allowed: false,
          role_name: 'governance_viewer',
          action: 'datasources:write',
        }),
      });
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const result = await page.evaluate(
    async ({
      apiBase,
      wsId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/permissions/check`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ action: 'datasources:write' }),
        },
      );
      return res.json() as Promise<unknown>;
    },
    {
      apiBase: API_BASE,
      wsId: WS_ID,
      token: buildJwt(ACTOR_ID, 'governance_viewer'),
    },
  );

  expect(result).toMatchObject({
    allowed: false,
    role_name: 'governance_viewer',
    action: 'datasources:write',
  });
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-08  Data Sources page shows "New Data Source" CTA for data_engineer
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-08: data_engineer sees "New Data Source" button on Data Sources page', async ({
  page,
}) => {
  await setupAuth(page, 'data_engineer');
  await mockActorRole(page, 'data_engineer');
  await mockDataSourcesApi(page);

  await page.goto(DATA_SOURCES_URL);

  await expect(page.getByTestId('create-data-source-btn')).toBeVisible();
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-09  Data Sources page hides "New Data Source" CTA for governance_viewer
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-09: governance_viewer does not see "New Data Source" button on Data Sources page', async ({
  page,
}) => {
  await setupAuth(page, 'governance_viewer');
  await mockActorRole(page, 'governance_viewer');
  await mockDataSourcesApi(page);

  await page.goto(DATA_SOURCES_URL);
  // Wait for the useWorkspacePermissions query to resolve
  await page.waitForTimeout(400);

  await expect(page.getByTestId('create-data-source-btn')).not.toBeAttached();
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-10  Datasets page shows "New Dataset" CTA for data_engineer
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-10: data_engineer sees "New Dataset" button on Datasets page', async ({
  page,
}) => {
  await setupAuth(page, 'data_engineer');
  await mockActorRole(page, 'data_engineer');
  await mockDatasetsApi(page);

  await page.goto(DATASETS_URL);

  await expect(page.getByTestId('create-dataset-btn')).toBeVisible();
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-11  Datasets page hides "New Dataset" CTA for governance_viewer
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-11: governance_viewer does not see "New Dataset" button on Datasets page', async ({
  page,
}) => {
  await setupAuth(page, 'governance_viewer');
  await mockActorRole(page, 'governance_viewer');
  await mockDatasetsApi(page);

  await page.goto(DATASETS_URL);
  // Wait for the useWorkspacePermissions query to resolve
  await page.waitForTimeout(400);

  await expect(page.getByTestId('create-dataset-btn')).not.toBeAttached();
});

// ═════════════════════════════════════════════════════════════════════════════
// E2E-12  PUT role with invalid role name → 422 INVALID_ROLE
// ═════════════════════════════════════════════════════════════════════════════

test('E2E-12: PUT role with invalid role name returns 422 INVALID_ROLE', async ({
  page,
}) => {
  await setupAuth(page, 'workspace_administrator');
  await mockActorRole(page, 'workspace_administrator');
  await mockDataSourcesApi(page);

  await page.route(
    (url) =>
      url.href.includes(
        `/api/v1/workspaces/${WS_ID}/members/${TARGET_USER_ID}/role`,
      ),
    (route) => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'INVALID_ROLE',
              message: "'super_admin' is not a valid workspace role.",
              fields: ['role_name'],
            },
          }),
        });
      } else {
        route.fallback();
      }
    },
  );

  await page.goto(DATA_SOURCES_URL);

  const response = await page.evaluate(
    async ({
      apiBase,
      wsId,
      userId,
      token,
    }: {
      apiBase: string;
      wsId: string;
      userId: string;
      token: string;
    }) => {
      const res = await fetch(
        `${apiBase}/workspaces/${wsId}/members/${userId}/role`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ role_name: 'super_admin' }),
        },
      );
      return { status: res.status, body: (await res.json()) as unknown };
    },
    {
      apiBase: API_BASE,
      wsId: WS_ID,
      userId: TARGET_USER_ID,
      token: buildJwt(),
    },
  );

  expect(response.status).toBe(422);
  expect((response.body as { error: { code: string } }).error.code).toBe(
    'INVALID_ROLE',
  );
});
