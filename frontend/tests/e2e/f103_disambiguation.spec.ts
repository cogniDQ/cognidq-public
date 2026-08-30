import { test, expect } from '@playwright/test';

/**
 * F103 — Rule Disambiguation UI E2E Tests
 * Tests the disambiguation panel, candidate selection, and resolution flow.
 */

const WS_ID = 'test-ws-001';
const BASE = `/hub/ws/${WS_ID}/nl-rule-builder`;

// JWT helper for auth
function makeJWT() {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(JSON.stringify({ sub: 'user-1', exp: 9999999999 }));
  return `${header}.${payload}.test-sig`;
}

// Mock resolution response with disambiguation
const DISAMBIG_RESOLUTION = {
  resolved_rule: { rule_type: 'date_comparison', schema_version: '1.0', subject: { raw_text: 'shipping date' }, object: { raw_text: 'order date' }, operator: 'greater_than', confidence: 0.85, requires_disambiguation: true, parse_warnings: [] },
  subject_resolution: {
    raw_text: 'shipping date',
    candidates: [
      { asset_id: 'asset-1', column_name: 'shipping_date', dataset_name: 'Orders Curated', data_type: 'date', overall_score: 0.85, confidence_band: 'medium', signal_breakdown: [{ signal_name: 'lexical_match', score: 0.95, evidence: 'normalized match' }, { signal_name: 'glossary_match', score: 0.0, evidence: 'no glossary' }], evidence_summary: ['lexical_match'] },
      { asset_id: 'asset-2', column_name: 'ship_dt', dataset_name: 'Shipments Raw', data_type: 'date', overall_score: 0.71, confidence_band: 'medium', signal_breakdown: [{ signal_name: 'lexical_match', score: 0.60, evidence: 'fuzzy match' }], evidence_summary: ['lexical_match'] },
    ],
    best_candidate: { asset_id: 'asset-1', column_name: 'shipping_date', dataset_name: 'Orders Curated', data_type: 'date', overall_score: 0.85, confidence_band: 'medium', signal_breakdown: [], evidence_summary: ['lexical_match'] },
    requires_disambiguation: true,
  },
  object_resolution: {
    raw_text: 'order date',
    candidates: [
      { asset_id: 'asset-3', column_name: 'order_date', dataset_name: 'Orders Curated', data_type: 'date', overall_score: 0.95, confidence_band: 'high', signal_breakdown: [{ signal_name: 'lexical_match', score: 1.0, evidence: 'exact match' }], evidence_summary: ['lexical_match'] },
    ],
    best_candidate: { asset_id: 'asset-3', column_name: 'order_date', dataset_name: 'Orders Curated', data_type: 'date', overall_score: 0.95, confidence_band: 'high', signal_breakdown: [], evidence_summary: ['lexical_match'] },
    requires_disambiguation: false,
  },
  overall_confidence: 0.85,
  requires_disambiguation: true,
  resolution_evidence: { subject_candidates_count: 2, object_candidates_count: 1 },
};

// Mock high-confidence resolution (no disambiguation)
const HIGH_CONF_RESOLUTION = {
  ...DISAMBIG_RESOLUTION,
  overall_confidence: 0.95,
  requires_disambiguation: false,
  subject_resolution: {
    ...DISAMBIG_RESOLUTION.subject_resolution,
    requires_disambiguation: false,
    best_candidate: { ...DISAMBIG_RESOLUTION.subject_resolution.best_candidate!, overall_score: 0.95, confidence_band: 'high' },
  },
};

// Mock parse response
const PARSE_RESPONSE = {
  request_id: 'req-1',
  rule_text: 'shipping date must be after order date',
  sir: { rule_type: 'date_comparison', schema_version: '1.0', intent: 'Date comparison check', subject: { raw_text: 'shipping date', name: 'shipping date', role: 'subject' }, object: { raw_text: 'order date', name: 'order date', role: 'object' }, operator: 'greater_than', conditions: [], scope: {}, confidence: 0.92, needs_disambiguation: false, parse_warnings: [] },
  confidence: 0.92,
  needs_disambiguation: false,
  warnings: [],
  created_at: new Date().toISOString(),
};

test.beforeEach(async ({ page }) => {
  // Set auth cookie
  await page.context().addCookies([{ name: 'token', value: makeJWT(), domain: 'localhost', path: '/' }]);
  // Set localStorage auth
  await page.addInitScript((jwt: string) => {
    localStorage.setItem('token', jwt);
  }, makeJWT());
});

function mockAPIs(page: any) {
  // Mock datasets
  page.route(`**/workspaces/${WS_ID}/datasets`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ datasets: [] }) })
  );
  // Mock parse
  page.route(`**/workspaces/${WS_ID}/rule-builder/parse`, (route: any) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PARSE_RESPONSE) })
  );
}

test.describe('F103 Disambiguation UI', () => {

  test('T01: Disambiguation panel appears after resolve', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.waitForSelector('[data-testid="resolve-btn"]');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).toBeVisible();
  });

  test('T02: Warning banner shown for disambiguation', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="disambiguation-warning"]')).toBeVisible();
  });

  test('T03: Subject candidates are displayed', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="candidate-card-1"]')).toBeVisible();
    await expect(page.locator('[data-testid="candidate-card-2"]')).toBeVisible();
  });

  test('T04: Clicking candidate selects it', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await page.click('[data-testid="candidate-card-2"]');
    // Second card should now have blue ring
    await expect(page.locator('[data-testid="candidate-card-2"]')).toHaveClass(/ring-1/);
  });

  test('T05: Signal breakdown toggle works', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    // Click first signal toggle
    const toggle = page.locator('[data-testid="signal-toggle"]').first();
    await toggle.click();
    await expect(page.locator('[data-testid="signal-details"]').first()).toBeVisible();
  });

  test('T06: Accept resolution button works', async ({ page }) => {
    mockAPIs(page);
    let resolveCount = 0;
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) => {
      resolveCount++;
      const response = resolveCount === 1 ? DISAMBIG_RESOLUTION : HIGH_CONF_RESOLUTION;
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(response) });
    });

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await page.click('[data-testid="accept-resolution"]');
    // Should trigger re-resolve with override
    expect(resolveCount).toBe(2);
  });

  test('T07: Cancel resolution hides panel', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).toBeVisible();
    await page.click('[data-testid="cancel-resolution"]');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).not.toBeVisible();
  });

  test('T08: High confidence resolution shows no warning', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HIGH_CONF_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).toBeVisible();
    await expect(page.locator('[data-testid="disambiguation-warning"]')).not.toBeVisible();
  });

  test('T09: Entity sections show raw text', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="entity-section-subject"]')).toContainText('shipping date');
    await expect(page.locator('[data-testid="entity-section-object"]')).toContainText('order date');
  });

  test('T10: Resolve button disabled without parse result', async ({ page }) => {
    mockAPIs(page);
    await page.goto(BASE);
    const resolveBtn = page.locator('[data-testid="resolve-btn"]');
    await expect(resolveBtn).toBeDisabled();
  });

  test('T11: Candidate card shows dataset name', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="candidate-card-1"]')).toContainText('Orders Curated');
    await expect(page.locator('[data-testid="candidate-card-2"]')).toContainText('Shipments Raw');
  });

  test('T12: Clear button hides disambiguation panel', async ({ page }) => {
    mockAPIs(page);
    page.route(`**/workspaces/${WS_ID}/rule-builder/resolve`, (route: any) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DISAMBIG_RESOLUTION) })
    );

    await page.goto(BASE);
    await page.fill('textarea', 'shipping date must be after order date');
    await page.click('button:has-text("Interpret Rule")');
    await page.click('[data-testid="resolve-btn"]');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).toBeVisible();
    await page.click('button:has-text("Clear")');
    await expect(page.locator('[data-testid="disambiguation-panel"]')).not.toBeVisible();
  });
});
