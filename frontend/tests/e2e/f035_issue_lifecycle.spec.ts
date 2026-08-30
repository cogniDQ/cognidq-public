/**
 * F035 — Packet 4: Issue Assignment and Status Lifecycle
 *
 * E2E tests cover the primary user flows for the mutation panel:
 *
 *   E2E-01  Mutation panel displays allowed status transitions
 *   E2E-02  Status transition button sends PATCH and updates UI
 *   E2E-03  Resolution prompt appears for resolve/close without pre-existing summary
 *   E2E-04  Resolution submit sends PATCH with status + resolution_summary
 *   E2E-05  Due date control sends PATCH with due_at
 *   E2E-06  Unassign button sends PATCH with assignee_id: null
 *   E2E-07  Resolution summary card displayed when present
 *   E2E-08  Error toast on PATCH failure
 *
 * Mocking strategy: JWT in localStorage, all API calls intercepted via page.route()
 */

import { test, expect, Page } from '@playwright/test'

// ────────────────────────────────────────────────────────────────────────────
// JWT helper
// ────────────────────────────────────────────────────────────────────────────

function buildJwt(): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      email: 'test@example.com',
      actor_role: 'data_engineer',
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  )
  return `${header}.${payload}.fakesig`
}

// ────────────────────────────────────────────────────────────────────────────
// Fixtures
// ────────────────────────────────────────────────────────────────────────────

const WS = 'ws-test-f035'
const ISSUE_ID = 'iss-f035-001'

function makeIssue(overrides: Record<string, unknown> = {}) {
  return {
    id: ISSUE_ID,
    workspace_id: WS,
    tenant_id: 'tenant-001',
    flow_execution_id: 'exec-001',
    flow_node_result_id: null,
    rule_id: null,
    dataset_id: null,
    assignee_id: 'user-001',
    issue_type: 'rule_failure',
    severity: 'major',
    status: 'open',
    title: 'Test lifecycle issue',
    impact_summary: null,
    resolution_summary: null,
    failure_count: 10,
    rows_scanned: 100,
    pass_rate: 90.0,
    due_at: null,
    opened_at: new Date().toISOString(),
    resolved_at: null,
    closed_at: null,
    updated_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    rule: null,
    dataset: null,
    assignee: { id: 'user-001', display_name: 'Jane Doe', email: 'jane@example.com' },
    flow_execution: null,
    node_result: null,
    ...overrides,
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Setup helpers
// ────────────────────────────────────────────────────────────────────────────

async function setupAuth(page: Page) {
  await page.addInitScript((token: string) => {
    window.localStorage.setItem('access_token', token)
  }, buildJwt())
}

async function mockDetailApi(page: Page, issue: object) {
  await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(issue),
      })
    }
    return route.continue()
  })
}

async function mockPatchApi(page: Page, response: object, statusCode = 200) {
  await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: statusCode,
        contentType: 'application/json',
        body: JSON.stringify(response),
      })
    }
    return route.continue()
  })
}

async function mockBothApis(page: Page, getIssue: object, patchResponse: object, patchStatus = 200) {
  await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(getIssue),
      })
    }
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: patchStatus,
        contentType: 'application/json',
        body: JSON.stringify(patchResponse),
      })
    }
    return route.continue()
  })
}

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F035 Issue Lifecycle Mutation Panel', () => {
  test('E2E-01: Mutation panel displays allowed status transitions for open issue', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'open' })
    await mockDetailApi(page, issue)

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)

    await expect(page.getByTestId('mutation-panel')).toBeVisible()
    await expect(page.getByTestId('status-transition')).toBeVisible()
    // open → in_progress, resolved, closed
    await expect(page.getByTestId('transition-in_progress')).toBeVisible()
    await expect(page.getByTestId('transition-resolved')).toBeVisible()
    await expect(page.getByTestId('transition-closed')).toBeVisible()
  })

  test('E2E-02: Status transition sends PATCH and updates UI', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'open' })
    const updated = makeIssue({ status: 'in_progress' })
    await mockBothApis(page, issue, updated)

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('transition-in_progress').click()

    // Toast confirmation
    await expect(page.getByText('Issue updated')).toBeVisible({ timeout: 5000 })
  })

  test('E2E-03: Resolution prompt appears for resolve without pre-existing summary', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'open', resolution_summary: null })
    await mockDetailApi(page, issue)

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('transition-resolved').click()

    // Resolution prompt should appear
    await expect(page.getByTestId('resolution-prompt')).toBeVisible()
    await expect(page.getByTestId('resolution-input')).toBeVisible()
    await expect(page.getByTestId('resolution-submit')).toBeVisible()
    await expect(page.getByTestId('resolution-cancel')).toBeVisible()
  })

  test('E2E-04: Resolution submit sends PATCH with status + resolution_summary', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'open', resolution_summary: null })
    const resolved = makeIssue({ status: 'resolved', resolution_summary: 'Fixed the pipeline' })

    let patchBody: string | undefined
    await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issue),
        })
      }
      if (route.request().method() === 'PATCH') {
        patchBody = route.request().postData() ?? undefined
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(resolved),
        })
      }
      return route.continue()
    })

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('transition-resolved').click()
    await page.getByTestId('resolution-input').fill('Fixed the pipeline')
    await page.getByTestId('resolution-submit').click()

    await expect(page.getByText('Issue updated')).toBeVisible({ timeout: 5000 })
    expect(patchBody).toBeDefined()
    const parsed = JSON.parse(patchBody!)
    expect(parsed.status).toBe('resolved')
    expect(parsed.resolution_summary).toBe('Fixed the pipeline')
  })

  test('E2E-05: Due date control sends PATCH with due_at', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue()
    const updated = makeIssue({ due_at: '2026-06-15T00:00:00Z' })

    let patchBody: string | undefined
    await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issue),
        })
      }
      if (route.request().method() === 'PATCH') {
        patchBody = route.request().postData() ?? undefined
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updated),
        })
      }
      return route.continue()
    })

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('due-at-input').fill('2026-06-15')
    await page.getByTestId('due-at-save').click()

    await expect(page.getByText('Issue updated')).toBeVisible({ timeout: 5000 })
    expect(patchBody).toBeDefined()
    const parsed = JSON.parse(patchBody!)
    expect(parsed.due_at).toBe('2026-06-15')
  })

  test('E2E-06: Unassign button sends PATCH with assignee_id null', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue()
    const updated = makeIssue({ assignee_id: null, assignee: null })

    let patchBody: string | undefined
    await page.route(`**/api/v1/workspaces/${WS}/issues/${ISSUE_ID}`, (route) => {
      if (route.request().method() === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(issue),
        })
      }
      if (route.request().method() === 'PATCH') {
        patchBody = route.request().postData() ?? undefined
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updated),
        })
      }
      return route.continue()
    })

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('unassign-btn').click()

    await expect(page.getByText('Issue updated')).toBeVisible({ timeout: 5000 })
    expect(patchBody).toBeDefined()
    const parsed = JSON.parse(patchBody!)
    expect(parsed.assignee_id).toBeNull()
  })

  test('E2E-07: Resolution summary card displayed when present', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'resolved', resolution_summary: 'Fixed root cause in ETL' })
    await mockDetailApi(page, issue)

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)

    await expect(page.getByTestId('resolution-card')).toBeVisible()
    await expect(page.getByText('Fixed root cause in ETL')).toBeVisible()
  })

  test('E2E-08: Error toast on PATCH failure', async ({ page }) => {
    await setupAuth(page)
    const issue = makeIssue({ status: 'open' })
    await mockBothApis(
      page,
      issue,
      { detail: 'Transition not allowed' },
      422,
    )

    await page.goto(`/workspaces/${WS}/issues/${ISSUE_ID}`)
    await page.getByTestId('transition-in_progress').click()

    await expect(page.getByText('Transition not allowed')).toBeVisible({ timeout: 5000 })
  })
})
