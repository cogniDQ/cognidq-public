/**
 * F100 — NL Rule Intake UI
 *
 * E2E tests for the Natural Language Rule Builder page.
 *
 *   E2E-01  Page renders with header, textarea, examples, context panel
 *   E2E-02  Typing rule text updates character counter
 *   E2E-03  Clicking example suggestion populates textarea
 *   E2E-04  Interpret Rule button calls parse API and shows result
 *   E2E-05  Parse error displays error alert
 *   E2E-06  High confidence result (≥0.90) shows green badge
 *   E2E-07  Low confidence result (<0.70) shows disambiguation warning
 *   E2E-08  Clear button resets form
 *   E2E-09  Generate Flow button is disabled with tooltip
 *   E2E-10  Severity dropdown changes value
 *   E2E-11  Tag input accepts tags
 *   E2E-12  Dataset selector loads options from API
 *   E2E-13  Recent parses section shows after successful parse
 *   E2E-14  Clicking recent parse restores rule text
 *
 * Mocking strategy: JWT in localStorage, all API calls intercepted via page.route()
 */

import { test, expect, Page } from '@playwright/test';

// ────────────────────────────────────────────────────────────────────────────
// JWT helper
// ────────────────────────────────────────────────────────────────────────────

function buildJwt(actorRole: string): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      email: 'test@example.com',
      actor_role: actorRole,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

// ────────────────────────────────────────────────────────────────────────────
// Fixtures
// ────────────────────────────────────────────────────────────────────────────

const WORKSPACE_ID = 'ws-test-001';

const DATASETS_FIXTURE = [
  { id: 'ds-001', name: 'Employee Records', dataset_id: 'ds-001' },
  { id: 'ds-002', name: 'Invoice Data', dataset_id: 'ds-002' },
  { id: 'ds-003', name: 'Customer Profiles', dataset_id: 'ds-003' },
];

const HIGH_CONFIDENCE_RESPONSE = {
  request_id: 'req-001',
  rule_text: 'Customer email must not be null',
  sir: {
    rule_type: 'not_null',
    intent: 'Ensure customer email addresses are always populated',
    subject: { name: 'customer email', role: 'subject', resolved_column: 'email' },
    conditions: [{ operator: 'is_not_null' }],
    confidence: 0.95,
    needs_disambiguation: false,
    schema_version: '1.0',
  },
  confidence: 0.95,
  needs_disambiguation: false,
  warnings: [],
  created_at: new Date().toISOString(),
};

const LOW_CONFIDENCE_RESPONSE = {
  request_id: 'req-002',
  rule_text: 'amount should match total',
  sir: {
    rule_type: 'column_comparison',
    intent: 'Compare amount to total',
    subject: { name: 'amount', role: 'subject' },
    object: { name: 'total', role: 'object' },
    conditions: [{ operator: 'equals' }],
    confidence: 0.55,
    needs_disambiguation: true,
    disambiguation_reason: 'Multiple columns named "amount" found across datasets',
    alternatives: ['invoice_amount vs invoice_total', 'payment_amount vs order_total'],
    schema_version: '1.0',
  },
  confidence: 0.55,
  needs_disambiguation: true,
  warnings: ['Ambiguous column reference: "amount"'],
  created_at: new Date().toISOString(),
};

// ────────────────────────────────────────────────────────────────────────────
// Setup helpers
// ────────────────────────────────────────────────────────────────────────────

async function setupPage(page: Page, jwt?: string) {
  const token = jwt || buildJwt('workspace_admin');

  await page.addInitScript((t) => {
    localStorage.setItem('access_token', t);
    localStorage.setItem('selected_workspace_id', 'ws-test-001');
  }, token);

  // Mock workspace endpoint
  await page.route('**/api/v1/workspaces*', (route) => {
    if (route.request().method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { workspace_id: WORKSPACE_ID, name: 'Test Workspace', status: 'active' },
        ]),
      });
    }
    return route.continue();
  });

  // Mock datasets endpoint
  await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/datasets*`, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ datasets: DATASETS_FIXTURE }),
    });
  });

  // Mock user/me endpoint
  await page.route('**/api/v1/users/me*', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'test-user-id',
        email: 'test@example.com',
        full_name: 'Test User',
      }),
    });
  });

  // Mock workspace members/permissions
  await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/members/me/permissions*`, (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        permissions: ['rules:read', 'rules:write', 'datasets:read', 'executions:read'],
      }),
    });
  });
}

const PAGE_URL = `/hub/ws/${WORKSPACE_ID}/nl-rule-builder`;

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F100 — NL Rule Intake UI', () => {
  test('E2E-01: Page renders with header, textarea, examples, and context panel', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    await expect(page.getByRole('heading', { name: /NL Rule Builder/i })).toBeVisible();
    await expect(page.locator('#rule-text')).toBeVisible();
    await expect(page.getByText('Try these examples:')).toBeVisible();
    await expect(page.getByText('Context (optional)')).toBeVisible();
    await expect(page.getByRole('button', { name: /Interpret Rule/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Generate Flow/i })).toBeVisible();
  });

  test('E2E-02: Typing rule text updates character counter', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const textarea = page.locator('#rule-text');
    await textarea.fill('Customer email must not be null');
    await expect(page.getByText('31/500')).toBeVisible();
  });

  test('E2E-03: Clicking example suggestion populates textarea', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    await page.getByRole('button', { name: /Not null check/i }).click();
    const textarea = page.locator('#rule-text');
    await expect(textarea).toHaveValue('Customer email must not be null');
  });

  test('E2E-04: Interpret Rule calls parse API and shows result', async ({ page }) => {
    await setupPage(page);

    // Mock parse API
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/rule-builder/parse`, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(HIGH_CONFIDENCE_RESPONSE),
      });
    });

    await page.goto(PAGE_URL);

    const textarea = page.locator('#rule-text');
    await textarea.fill('Customer email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    // Wait for result panel
    await expect(page.getByText('Parse Result')).toBeVisible();
    await expect(page.getByText('95%')).toBeVisible();
    await expect(page.getByText('not null')).toBeVisible();
    await expect(page.getByText('customer email')).toBeVisible();
  });

  test('E2E-05: Parse error displays error alert', async ({ page }) => {
    await setupPage(page);

    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/rule-builder/parse`, (route) => {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Rule text is too ambiguous' }),
      });
    });

    await page.goto(PAGE_URL);

    const textarea = page.locator('#rule-text');
    await textarea.fill('something vague');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    // Error toast should appear
    await expect(page.getByText(/Rule text is too ambiguous|Failed to parse/i)).toBeVisible({ timeout: 5000 });
  });

  test('E2E-06: High confidence result shows green badge', async ({ page }) => {
    await setupPage(page);

    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/rule-builder/parse`, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(HIGH_CONFIDENCE_RESPONSE),
      });
    });

    await page.goto(PAGE_URL);
    await page.locator('#rule-text').fill('Customer email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    await expect(page.getByText('95%')).toBeVisible();
    await expect(page.getByText('High')).toBeVisible();
  });

  test('E2E-07: Low confidence result shows disambiguation warning', async ({ page }) => {
    await setupPage(page);

    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/rule-builder/parse`, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(LOW_CONFIDENCE_RESPONSE),
      });
    });

    await page.goto(PAGE_URL);
    await page.locator('#rule-text').fill('amount should match total');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    await expect(page.getByText('Disambiguation Required')).toBeVisible();
    await expect(page.getByText(/Multiple columns/i)).toBeVisible();
    await expect(page.getByText('55%')).toBeVisible();
  });

  test('E2E-08: Clear button resets form', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const textarea = page.locator('#rule-text');
    await textarea.fill('Some rule text');
    await expect(textarea).toHaveValue('Some rule text');

    await page.getByRole('button', { name: /Clear/i }).click();
    await expect(textarea).toHaveValue('');
  });

  test('E2E-09: Generate Flow button is disabled', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const btn = page.getByRole('button', { name: /Generate Flow/i });
    await expect(btn).toBeDisabled();
    await expect(btn).toHaveAttribute('title', 'Coming in a future release');
  });

  test('E2E-10: Severity dropdown changes value', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const select = page.locator('#severity-select');
    await expect(select).toHaveValue('major');
    await select.selectOption('critical');
    await expect(select).toHaveValue('critical');
  });

  test('E2E-11: Tag input accepts tags', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const tagInput = page.locator('#tags-input');
    await tagInput.fill('finance');
    await tagInput.press('Enter');

    await expect(page.getByText('finance')).toBeVisible();
    await expect(page.getByText('1/10 tags')).toBeVisible();
  });

  test('E2E-12: Dataset selector loads options from API', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);

    const select = page.locator('#dataset-select');
    await expect(select).toBeVisible();

    // Check options loaded
    const options = select.locator('option');
    // Default "— Select dataset —" + 3 datasets
    await expect(options).toHaveCount(4);
    await expect(options.nth(1)).toHaveText('Employee Records');
  });

  test('E2E-13: Recent parses section shows after successful parse', async ({ page }) => {
    await setupPage(page);

    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/rule-builder/parse`, (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(HIGH_CONFIDENCE_RESPONSE),
      });
    });

    await page.goto(PAGE_URL);
    await page.locator('#rule-text').fill('Customer email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    await expect(page.getByText('Recent Parses')).toBeVisible();
    await expect(page.getByText('Customer email must not be null').last()).toBeVisible();
  });

  test('E2E-14: Clicking recent parse restores rule text', async ({ page }) => {
    await setupPage(page);

    // Pre-populate history in localStorage
    await page.addInitScript(() => {
      localStorage.setItem(
        'nl-rule-history-ws-test-001',
        JSON.stringify([
          {
            rule_text: 'Old rule from history',
            confidence: 0.88,
            rule_type: 'not_null',
            timestamp: new Date().toISOString(),
          },
        ]),
      );
    });

    await page.goto(PAGE_URL);

    // Click the history entry
    await page.getByText('Old rule from history').click();

    const textarea = page.locator('#rule-text');
    await expect(textarea).toHaveValue('Old rule from history');
  });
});
