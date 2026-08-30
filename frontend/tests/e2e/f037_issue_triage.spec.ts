/**
 * F037 — Packet 3: Issue List Triage Controls
 *
 * E2E tests for the enhanced issue list with filters, sort, and export:
 *
 *   E2E-01  Assignee filter input renders and updates URL params
 *   E2E-02  Dataset filter input renders and updates URL params
 *   E2E-03  Overdue toggle filters the list
 *   E2E-04  Column sort click sets sort_by/sort_dir in URL and shows indicator
 *   E2E-05  Clear filters button resets all filter params
 *   E2E-06  Export CSV button triggers download
 *   E2E-07  Overdue badge is displayed on overdue issues
 *   E2E-08  Assignee and Dataset columns render in the table
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

const WS = 'ws-test-f037'
const pastDate = new Date(Date.now() - 86_400_000).toISOString() // 1 day ago
const futureDate = new Date(Date.now() + 86_400_000 * 7).toISOString() // 7 days ahead

function makeIssueListItem(overrides: Record<string, unknown> = {}) {
  return {
    id: 'iss-001',
    workspace_id: WS,
    issue_type: 'rule_failure',
    severity: 'major',
    status: 'open',
    title: 'Null check failed',
    impact_summary: 'Affects 50 rows',
    failure_count: 10,
    due_at: futureDate,
    opened_at: pastDate,
    assignee_id: 'user-001',
    assignee_display_name: 'Jane Doe',
    dataset_name: 'sales_orders',
    updated_at: pastDate,
    ...overrides,
  }
}

function makeIssuePage(items: object[] = [makeIssueListItem()]) {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 25,
    has_next: false,
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

async function mockListApi(page: Page, responseBody: object) {
  await page.route(`**/api/v1/workspaces/${WS}/issues?*`, (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responseBody),
      })
    }
    return route.continue()
  })
  // Also catch the base URL without query params
  await page.route(`**/api/v1/workspaces/${WS}/issues`, (route) => {
    if (route.request().method() === 'GET' && !route.request().url().includes('/export')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responseBody),
      })
    }
    return route.continue()
  })
}

const LIST_URL = `/workspaces/${WS}/issues`

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F037 Issue Triage Controls', () => {
  test('E2E-01: assignee filter input renders and updates URL', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())
    await page.goto(LIST_URL)

    const input = page.getByTestId('assignee-filter')
    await expect(input).toBeVisible()
    await input.fill('user-001')

    // URL should include assignee_id param
    await expect(page).toHaveURL(/assignee_id=user-001/)
  })

  test('E2E-02: dataset filter input renders and updates URL', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())
    await page.goto(LIST_URL)

    const input = page.getByTestId('dataset-filter')
    await expect(input).toBeVisible()
    await input.fill('ds-001')

    await expect(page).toHaveURL(/dataset_id=ds-001/)
  })

  test('E2E-03: overdue toggle updates URL params', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())
    await page.goto(LIST_URL)

    const checkbox = page.getByTestId('overdue-filter')
    await expect(checkbox).toBeVisible()
    await checkbox.check()

    await expect(page).toHaveURL(/overdue=true/)
  })

  test('E2E-04: column sort click sets sort_by/sort_dir and shows indicator', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())
    await page.goto(LIST_URL)

    // Click severity header to set ascending sort
    const severityHeader = page.getByTestId('sort-severity')
    await severityHeader.click()

    await expect(page).toHaveURL(/sort_by=severity/)
    await expect(page).toHaveURL(/sort_dir=asc/)

    // Ascending indicator should be visible
    await expect(page.getByTestId('sort-asc-severity')).toBeVisible()

    // Click again to toggle to descending
    await severityHeader.click()
    await expect(page).toHaveURL(/sort_dir=desc/)
    await expect(page.getByTestId('sort-desc-severity')).toBeVisible()
  })

  test('E2E-05: clear filters button resets filter params', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())
    await page.goto(`${LIST_URL}?status=open&severity=critical&overdue=true`)

    const clearBtn = page.getByTestId('clear-filters')
    await expect(clearBtn).toBeVisible()
    await clearBtn.click()

    // Filter params should be gone
    const url = page.url()
    expect(url).not.toContain('status=')
    expect(url).not.toContain('severity=')
    expect(url).not.toContain('overdue=')

    // Clear button should be hidden now
    await expect(clearBtn).not.toBeVisible()
  })

  test('E2E-06: export CSV button triggers download', async ({ page }) => {
    await setupAuth(page)
    await mockListApi(page, makeIssuePage())

    // Mock the export endpoint
    await page.route(`**/api/v1/workspaces/${WS}/issues/export*`, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'text/csv; charset=utf-8',
        headers: {
          'content-disposition': 'attachment; filename="issues_export_20250101_120000.csv"',
        },
        body: 'id,title\niss-001,Null check failed\n',
      })
    })

    await page.goto(LIST_URL)

    const exportBtn = page.getByTestId('export-csv')
    await expect(exportBtn).toBeVisible()

    // Listen for download event
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      exportBtn.click(),
    ])

    expect(download).toBeTruthy()
  })

  test('E2E-07: overdue badge displayed on overdue issues', async ({ page }) => {
    await setupAuth(page)
    const overdueItem = makeIssueListItem({
      due_at: pastDate,
      status: 'open',
    })
    await mockListApi(page, makeIssuePage([overdueItem]))
    await page.goto(LIST_URL)

    const badge = page.getByTestId('overdue-badge')
    await expect(badge).toBeVisible()
    await expect(badge).toHaveText('OVERDUE')
  })

  test('E2E-08: assignee and dataset columns render in table', async ({ page }) => {
    await setupAuth(page)
    const item = makeIssueListItem({
      assignee_display_name: 'Bob Smith',
      dataset_name: 'inventory_data',
    })
    await mockListApi(page, makeIssuePage([item]))
    await page.goto(LIST_URL)

    const assigneeCell = page.getByTestId('assignee-cell')
    await expect(assigneeCell).toHaveText('Bob Smith')

    const datasetCell = page.getByTestId('dataset-cell')
    await expect(datasetCell).toHaveText('inventory_data')
  })
})
