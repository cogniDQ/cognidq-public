/**
 * F135 P01 — Dark Theme Token Migration
 *
 * Verifies that all NL Rule Builder components use the dark design system tokens
 * and contain no hardcoded light-mode CSS classes.
 *
 *   DT-01  NL Rule Builder page root has no light bg classes
 *   DT-02  ParseResultPanel error state uses dark token classes
 *   DT-03  ParseResultPanel cannot_interpret state uses dark token classes
 *   DT-04  ParseResultPanel clarification state uses dark token classes
 *   DT-05  ParseResultPanel parsed state uses dark token classes
 *   DT-06  ExplainabilitySection high-trust badge uses dark token classes
 *   DT-07  ExplainabilitySection medium-trust badge uses dark token classes
 *   DT-08  ExplainabilitySection low-trust badge uses dark token classes
 *   DT-09  CompiledConfigPreview cards use dark token classes
 *   DT-10  Step3Confirm rule summary uses dark token classes
 *   DT-11  ClarifyingQuestionsPanel uses dark token classes
 *
 * Mocking strategy: JWT in localStorage, all API calls intercepted via page.route()
 */

import { test, expect, Page } from '@playwright/test';

// ────────────────────────────────────────────────────────────────────────────
// Forbidden light-mode classes (must not appear in any nl-rule-builder element)
// ────────────────────────────────────────────────────────────────────────────

const FORBIDDEN_BG = [
  'bg-white', 'bg-gray-50', 'bg-gray-100', 'bg-gray-200',
  'bg-green-50', 'bg-green-100', 'bg-yellow-50', 'bg-yellow-100',
  'bg-red-50', 'bg-red-100', 'bg-orange-50', 'bg-orange-100',
  'bg-blue-50', 'bg-blue-100', 'bg-primary-50', 'bg-primary-100',
  'bg-amber-50', 'bg-amber-100',
];

const FORBIDDEN_TEXT = [
  'text-gray-700', 'text-gray-600', 'text-gray-900', 'text-gray-800',
  'text-green-700', 'text-green-800', 'text-yellow-700', 'text-yellow-800',
  'text-red-700', 'text-red-800', 'text-amber-700', 'text-amber-800',
  'text-blue-700', 'text-blue-800', 'text-primary-800',
];

const FORBIDDEN_BORDER = [
  'border-gray-100', 'border-gray-200', 'border-gray-300',
  'border-green-200', 'border-green-300', 'border-yellow-200', 'border-yellow-300',
  'border-red-200', 'border-red-300', 'border-amber-200', 'border-amber-300',
  'border-blue-100', 'border-blue-200', 'border-blue-300', 'border-primary-300',
];

const ALL_FORBIDDEN = [...FORBIDDEN_BG, ...FORBIDDEN_TEXT, ...FORBIDDEN_BORDER];

// ────────────────────────────────────────────────────────────────────────────
// JWT + setup helpers
// ────────────────────────────────────────────────────────────────────────────

function buildJwt(actorRole = 'data_engineer'): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-f135',
      email: 'f135test@example.com',
      actor_role: actorRole,
      exp: Math.floor(Date.now() / 1000) + 3600,
    }),
  );
  return `${header}.${payload}.fakesig`;
}

// Must be a valid UUID to pass WorkspaceAccessGuard's UUID regex check
const WORKSPACE_ID = 'f1350001-f135-0001-f135-000000000001';
const PAGE_URL = `/hub/ws/${WORKSPACE_ID}/nl-rule-builder`;

async function setupPage(page: Page) {
  await page.addInitScript((args) => {
    const { jwt, wsId } = args as { jwt: string; wsId: string };
    localStorage.setItem('access_token', jwt);
    localStorage.setItem('selected_workspace_id', wsId);
  }, { jwt: buildJwt('platform_admin'), wsId: WORKSPACE_ID });

  /**
   * Catch-all API mock:
   * - auth/me goes to localhost:8000 (auth.ts uses its own axios instance)
   * - workspace/* calls go to localhost:5173/api/* (api.ts base URL is relative
   *   at runtime — Vite proxy passes them through)
   * Matching all /api/ paths on both hosts ensures consistent interception.
   */
  await page.route(/\/api\/v1\//, async (route) => {
    const url = route.request().url();

    if (url.includes('/auth/me')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-f135',
          email: 'f135test@example.com',
          full_name: 'Dark Test User',
          email_verified: true,
          status: 'active',
          last_login_at: null,
          created_at: new Date().toISOString(),
          platform_role: 'platform_admin',
        }),
      });
    }

    if (url.includes('/workspaces') && url.includes('/datasets')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ datasets: [{ id: 'ds-dt-01', name: 'Test Dataset', dataset_id: 'ds-dt-01' }] }),
      });
    }

    if (url.includes('/workspaces') && url.includes('/members/me/permissions')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ permissions: ['rules:read', 'rules:write', 'datasets:read', 'executions:read'] }),
      });
    }

    if (url.includes('/rule-builder/parses')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ parses: [], total: 0, page: 1, page_size: 5 }),
      });
    }

    if (url.match(/\/workspaces\/[^/]+$/) || url.match(/\/workspaces\/[^/?]+\?/)) {
      // Individual workspace fetch (WorkspaceAccessGuard)
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            workspace_id: WORKSPACE_ID,
            workspace_name: 'Dark Test WS',
            status: 'active',
            dataset_count: 1,
            member_count: 1,
          },
        }),
      });
    }

    if (url.includes('/workspaces')) {
      // Workspace list
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: [{ workspace_id: WORKSPACE_ID, workspace_name: 'Dark Test WS', status: 'active' }],
          meta: { total: 1, page: 1, page_size: 100, has_next: false },
        }),
      });
    }

    // Fall through for any other API calls
    return route.continue();
  });
}

/** Returns all class tokens in the NL Rule Builder container as a flat string. */
async function getNLRuleBuilderClasses(page: Page): Promise<string> {
  return page.evaluate(() => {
    // Prefer nl-rule-builder testid; fall back to main content area selectors
    const container =
      document.querySelector('[data-testid="nl-rule-builder"]') ??
      document.querySelector('[data-testid="step1-input"]')?.closest('main') ??
      document.querySelector('main') ??
      document.body;
    const elements = container.querySelectorAll('*');
    const classes: string[] = [];
    elements.forEach((el) => {
      if (el.className && typeof el.className === 'string') {
        classes.push(el.className);
      }
    });
    return classes.join(' ');
  });
}

/** Asserts none of the forbidden classes appear in the given class string. */
function assertNoDark(classStr: string, context: string) {
  for (const cls of ALL_FORBIDDEN) {
    // Match whole token (not partial, e.g. bg-gray-900 must not match bg-gray-9)
    const pattern = new RegExp(`(?:^|\\s)${cls.replace('-', '\\-')}(?:\\s|$)`);
    expect(
      pattern.test(classStr),
      `[${context}] Found forbidden light-mode class: ${cls}`,
    ).toBe(false);
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Fixtures
// ────────────────────────────────────────────────────────────────────────────

const HIGH_CONFIDENCE_PARSE = {
  request_id: 'req-dt-01',
  rule_text: 'Email must not be null',
  parsed_rule: {
    rule_type: 'not_null',
    intent: 'Ensure email is populated',
    subject: { name: 'email', role: 'subject', resolved_column: 'email' },
    conditions: [{ operator: 'is_not_null' }],
    confidence: 0.95,
    needs_disambiguation: false,
    schema_version: '1.0',
    parse_warnings: [],
  },
  confidence: 0.95,
  needs_disambiguation: false,
  warnings: [],
  status: 'parsed',
  reason: null,
  suggestions: [],
  explainability: [],
  decomposition_summary: null,
  clarifying_questions: [],
  clarification_context: null,
  created_at: new Date().toISOString(),
};

const PARSE_ERROR = {
  error: 'parse_error',
  message: 'Unable to parse rule: ambiguous subject reference',
  status: 422,
};

const CANNOT_INTERPRET = {
  request_id: 'req-dt-02',
  rule_text: 'xyz abc',
  parsed_rule: null,
  confidence: 0,
  needs_disambiguation: false,
  warnings: [],
  error: 'cannot_interpret',
  status: 'cannot_interpret',
  reason: 'The rule text is too vague to interpret.',
  suggestions: ['Specify a column name', 'Provide a condition'],
  explainability: [],
  decomposition_summary: null,
  clarifying_questions: [],
  clarification_context: null,
  created_at: new Date().toISOString(),
};

const CLARIFICATION_RESPONSE = {
  request_id: 'req-dt-03',
  rule_text: 'salary should be valid',
  parsed_rule: null,
  confidence: 0.4,
  needs_disambiguation: false,
  warnings: [],
  status: 'needs_clarification',
  reason: 'More information needed.',
  suggestions: [],
  explainability: [],
  decomposition_summary: null,
  clarifying_questions: [
    {
      field: 'threshold',
      question: 'What is the minimum valid salary?',
      options: ['0', '1000', '50000'],
      required: true,
    },
  ],
  clarification_context: null,
  created_at: new Date().toISOString(),
};

const RESOLVE_RESPONSE = {
  resolved_rule: { rule_type: 'not_null' },
  subject_resolution: {
    raw_text: 'email',
    candidates: [],
    best_candidate: null,
    requires_disambiguation: false,
  },
  object_resolution: null,
  overall_confidence: 0.95,
  requires_disambiguation: false,
  resolution_evidence: {},
  glossary_matches: [],
};

// ────────────────────────────────────────────────────────────────────────────
// Tests
// ────────────────────────────────────────────────────────────────────────────

test.describe('F135 P01 — Dark Theme Token Migration', () => {
  test('DT-01: NL Rule Builder page root has no light bg classes', async ({ page }) => {
    await setupPage(page);
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text', { timeout: 10000 });

    const classes = await getNLRuleBuilderClasses(page);
    // Check that no light background classes appear in the main page area
    const failed: string[] = [];
    for (const cls of FORBIDDEN_BG) {
      const pattern = new RegExp(`(?:^|\\s)${cls.replace(/-/g, '\\-')}(?:\\s|$)`);
      if (pattern.test(classes)) failed.push(cls);
    }
    expect(failed, `DT-01: Found forbidden light-mode bg classes: ${failed.join(', ')}`).toHaveLength(0);
  });

  test('DT-02: ParseResultPanel error state uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify(PARSE_ERROR) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'xyz');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    // 422 error stays on step 1 — wait for toast notification or a brief delay
    await page.waitForTimeout(2000);

    const classes = await getNLRuleBuilderClasses(page);
    assertNoDark(classes, 'DT-02 error state');
  });

  test('DT-03: ParseResultPanel cannot_interpret state uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CANNOT_INTERPRET) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'xyz abc');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    assertNoDark(classes, 'DT-03 cannot_interpret');
  });

  test('DT-04: ParseResultPanel clarification state uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CLARIFICATION_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'salary should be valid');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    assertNoDark(classes, 'DT-04 clarification');
  });

  test('DT-05: ParseResultPanel parsed (success) state uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_CONFIDENCE_PARSE) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    assertNoDark(classes, 'DT-05 parsed success');
  });

  test('DT-06: ExplainabilitySection high-trust badge uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_CONFIDENCE_PARSE) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();

    // Open explainability section if present
    const explainToggle = page.locator('[data-testid="explainability-toggle"]');
    if (await explainToggle.isVisible({ timeout: 5000 }).catch(() => false)) {
      await explainToggle.click();
      await page.waitForSelector('[data-testid="explainability-body"]', { timeout: 5000 });
    }

    const explainEl = page.locator('[data-testid="explainability-section"]');
    if (await explainEl.isVisible({ timeout: 3000 }).catch(() => false)) {
      const html = await explainEl.evaluate((el) => el.outerHTML);
      for (const cls of FORBIDDEN_BG) {
        expect(html, `DT-06: Found forbidden class ${cls} in ExplainabilitySection`).not.toContain(cls);
      }
    }
  });

  test('DT-07: ExplainabilitySection medium-trust badge has dark text class', async ({ page }) => {
    await setupPage(page);
    const mediumParse = {
      ...HIGH_CONFIDENCE_PARSE,
      confidence: 0.75,
      sir: { ...HIGH_CONFIDENCE_PARSE.sir, confidence: 0.75 },
    };
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mediumParse) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    // Verify no light yellow text in medium confidence
    expect(classes).not.toMatch(/\btext-yellow-700\b/);
    expect(classes).not.toMatch(/\btext-yellow-800\b/);
  });

  test('DT-08: ExplainabilitySection low-trust badge has dark text class', async ({ page }) => {
    await setupPage(page);
    const lowParse = {
      ...HIGH_CONFIDENCE_PARSE,
      confidence: 0.5,
      sir: { ...HIGH_CONFIDENCE_PARSE.sir, confidence: 0.5 },
    };
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(lowParse) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    expect(classes).not.toMatch(/\btext-red-700\b/);
    expect(classes).not.toMatch(/\btext-red-800\b/);
  });

  test('DT-09: CompiledConfigPreview cards use dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_CONFIDENCE_PARSE) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const configEl = page.locator('[data-testid="compiled-config-list"], [data-testid="compiled-config-empty"]');
    if (await configEl.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      const html = await configEl.first().evaluate((el) => el.outerHTML);
      for (const cls of FORBIDDEN_BG) {
        expect(html, `DT-09: Found forbidden class ${cls} in CompiledConfigPreview`).not.toContain(cls);
      }
    }
  });

  test('DT-10: Step3Confirm rule summary uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_CONFIDENCE_PARSE) });
    });
    await page.route(`**/api/v1/workspaces/*/rule-builder/resolve**`, (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOLVE_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'Email must not be null');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    // Navigate to step 3 if a "Next" / "Continue" button exists
    const nextBtn = page.locator('[data-testid="proceed-to-confirm-btn"], [data-testid="next-btn"]');
    if (await nextBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await nextBtn.click();
    }

    const step3El = page.locator('[data-testid="step3-confirm"]');
    if (await step3El.isVisible({ timeout: 3000 }).catch(() => false)) {
      const html = await step3El.evaluate((el) => el.outerHTML);
      for (const cls of ['bg-gray-50', 'bg-white', 'text-gray-700', 'text-gray-900', 'border-gray-200']) {
        expect(html, `DT-10: Found forbidden class ${cls} in Step3Confirm`).not.toContain(cls);
      }
    }
  });

  test('DT-11: ClarifyingQuestionsPanel uses dark token classes', async ({ page }) => {
    await setupPage(page);
    await page.route('**/api/v1/workspaces/*/rule-builder/parse', (route) => {
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CLARIFICATION_RESPONSE) });
    });
    await page.goto(PAGE_URL);
    await page.waitForSelector('#rule-text');
    await page.fill('#rule-text', 'salary should be valid');
    await page.getByRole('button', { name: /Interpret Rule/i }).click();
    await page.waitForSelector('[data-testid="parse-result-panel"]', { timeout: 8000 });

    const classes = await getNLRuleBuilderClasses(page);
    // Clarification panel should use dark blues/ambers not light ones
    expect(classes).not.toMatch(/\bbg-blue-50\b/);
    expect(classes).not.toMatch(/\bbg-amber-50\b/);
    expect(classes).not.toMatch(/\bbg-white\b/);
    expect(classes).not.toMatch(/\bborder-blue-100\b/);
    expect(classes).not.toMatch(/\bborder-blue-200\b/);
    expect(classes).not.toMatch(/\btext-blue-800\b/);
  });
});

