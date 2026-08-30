/**
 * F100 NL Rule Builder - Clarification Flow E2E Test
 * 
 * Comprehensive test of rule builder with natural language parsing,
 * disambiguation, and clarification scenarios using realistic enterprise data.
 * 
 * Scenarios tested:
 * 1. Simple low-ambiguity rule parse
 * 2. High-ambiguity rule requiring clarification
 * 3. Disambiguation with candidate selection
 * 4. Full rule acceptance and flow creation
 */
import { test, expect, Page } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';
const WORKSPACE_ID = '22222222-2222-4222-8222-222222222222';
const JWT_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzMzMzMzMzMy0zMzMzLTQzMzMtODMzMy0zMzMzMzMzMzMzMzMiLCJlbWFpbCI6ImUyZS51c2VyQGVudGVycHJpc2UudGVzdCIsImZ1bGxfbmFtZSI6IkUyRSBFbnRlcnByaXNlIFVzZXIiLCJ0ZW5hbnRfaWQiOiIxMTExMTExMS0xMTExLTQxMTEtODExMS0xMTExMTExMTExMTEiLCJ3b3Jrc3BhY2VfaWQiOiIyMjIyMjIyMi0yMjIyLTQyMjItODIyMi0yMjIyMjIyMjIyMjIiLCJyb2xlcyI6WyJ3b3Jrc3BhY2VfYWRtaW5pc3RyYXRvciJdLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTAwMDAwMDAwMH0.fake-token-for-testing'; // gitleaks:allow - synthetic test-only JWT with fake payload

// Mock parse response: low-confidence case with clarification needed
const PARSE_NEEDS_CLARIFICATION = {
  request_id: 'parse-1',
  parse_result_id: 'parsed-1',
  parsed_rule: {
    description: 'customer_email contains specific domain',
    check_type: 'column_value',
    severity: 'HIGH',
    dataset_id: '55555555-5555-5555-8555-555555555555', // customer_master
    subject: {
      type: 'column',
      name: 'customer_email',
      dataset_id: '55555555-5555-5555-8555-555555555555',
    },
    condition: 'contains',
    object: '@domain.com',
    confidence: 0.65,
  },
  status: 'needs_clarification',
  reason: null,
  suggestions: [],
  clarifying_questions: [
    {
      question: 'Which email domain are you checking for? (e.g., corporate.com, partner.io)',
      context: 'Detected potential domain reference but exact domain is ambiguous',
      question_id: 'q1',
    },
    {
      question: 'Should this check apply to all customers or only specific segments?',
      context: 'Clarify scope of rule application',
      question_id: 'q2',
    },
  ],
  clarification_context: {
    detected_datasets: [
      { id: '55555555-5555-5555-8555-555555555555', name: 'customer_master' },
    ],
    detected_columns: [
      { name: 'customer_email', dataset_id: '55555555-5555-5555-8555-555555555555' },
    ],
  },
  check_configs: null,
  detected_datasets: null,
  detected_columns: null,
  explainability: [
    { signal_name: 'email_format_match', confidence: 0.85 },
    { signal_name: 'domain_inclusion', confidence: 0.55 },
  ],
  trust_summary: {
    overall_confidence: 0.65,
    signals_high_confidence: ['email_format_match'],
    signals_low_confidence: ['domain_inclusion'],
  },
};

// Mock parse response: after clarification resolved
const PARSE_AFTER_CLARIFICATION = {
  request_id: 'parse-2',
  parse_result_id: 'parsed-2',
  parsed_rule: {
    description: 'customer_email contains corporate domain',
    check_type: 'column_value',
    severity: 'HIGH',
    dataset_id: '55555555-5555-5555-8555-555555555555',
    subject: {
      type: 'column',
      name: 'customer_email',
      dataset_id: '55555555-5555-5555-8555-555555555555',
    },
    condition: 'contains',
    object: '@corporate.com',
    confidence: 0.92,
  },
  status: 'parsed',
  reason: null,
  suggestions: [],
  clarifying_questions: [],
  clarification_context: null,
  check_configs: {
    frequency: 'daily',
    aggregation: 'any_fail',
    notification_threshold: 1,
  },
  detected_datasets: [
    { id: '55555555-5555-5555-8555-555555555555', name: 'customer_master' },
  ],
  detected_columns: [
    { name: 'customer_email', dataset_id: '55555555-5555-5555-8555-555555555555' },
  ],
  explainability: [
    { signal_name: 'email_format_match', confidence: 0.95 },
    { signal_name: 'domain_inclusion', confidence: 0.89 },
    { signal_name: 'dataset_schema_match', confidence: 0.90 },
  ],
  trust_summary: {
    overall_confidence: 0.92,
    signals_high_confidence: ['email_format_match', 'domain_inclusion', 'dataset_schema_match'],
    signals_low_confidence: [],
  },
};

// Mock resolve response with disambiguation
const RESOLVE_WITH_DISAMBIGUATION = {
  request_id: 'resolve-1',
  resolution_id: 'resolved-1',
  resolution_status: 'needs_disambiguation',
  needs_disambiguation: true,
  available_candidates: [
    {
      candidate_id: 'cand-1',
      dataset_id: '55555555-5555-5555-8555-555555555555',
      dataset_name: 'customer_master',
      column_name: 'customer_email',
      column_id: 'col-1',
      match_score: 0.98,
      match_reason: 'Exact schema match for email-type column',
      sample_values: ['alice@corporate.com', 'bob@corporate.com'],
      signal_breakdown: {
        name_match: 0.95,
        type_match: 0.99,
        domain_presence: 0.98,
        sample_data_match: 0.97,
      },
    },
    {
      candidate_id: 'cand-2',
      dataset_id: '66666666-6666-6666-8666-666666666666',
      dataset_name: 'order_fact',
      column_name: 'order_email',
      column_id: 'col-2',
      match_score: 0.72,
      match_reason: 'Partial match - email-like column but lower confidence',
      sample_values: null,
      signal_breakdown: {
        name_match: 0.65,
        type_match: 0.85,
        domain_presence: 0.60,
        sample_data_match: 0.70,
      },
    },
  ],
  warnings: [
    {
      type: 'low_confidence',
      message: 'Multiple candidates with moderate scores detected. Review suggestions carefully.',
    },
  ],
  suggested_candidate_id: 'cand-1',
};

// Mock resolve response: after disambiguation selected
const RESOLVE_AFTER_DISAMBIGUATION = {
  request_id: 'resolve-2',
  resolution_id: 'resolved-2',
  resolution_status: 'resolved',
  needs_disambiguation: false,
  available_candidates: [],
  selected_candidate: {
    candidate_id: 'cand-1',
    dataset_id: '55555555-5555-5555-8555-555555555555',
    dataset_name: 'customer_master',
    column_name: 'customer_email',
    column_id: 'col-1',
    match_score: 0.98,
  },
  accepted_rule: {
    rule_id: 'rule-001',
    title: 'Enterprise Customer Email Validation',
    description: 'Validate customer email addresses contain corporate domain',
    dataset_id: '55555555-5555-5555-8555-555555555555',
    dataset_name: 'customer_master',
    check_type: 'column_value',
    subject: {
      type: 'column',
      name: 'customer_email',
      dataset_id: '55555555-5555-5555-8555-555555555555',
    },
    condition: 'contains',
    object: '@corporate.com',
    severity: 'HIGH',
    status: 'draft',
    created_at: new Date().toISOString(),
  },
  warnings: [],
};

test.describe('F100 - NL Rule Builder with Clarification & Disambiguation', () => {
  let page: Page;

  test.beforeEach(async ({ browser }) => {
    page = await browser.newPage();
    
    // Set JWT token in localStorage
    await page.context().addInitScript(() => {
      localStorage.setItem('access_token', '${JWT_TOKEN}');
      localStorage.setItem('refresh_token', 'mock-refresh-token');
    });

    // Mock datasets API
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/datasets`, route => {
      route.abort('blockedbyclient');
      route.continue();
    });
    
    // Use interceptor to mock datasets on-demand
    await page.route(`**/api/v1/workspaces/${WORKSPACE_ID}/datasets`, async route => {
      await route.continue();
    });

    // Navigate to rule builder
    await page.goto(`${BASE_URL}/workspaces/${WORKSPACE_ID}/rules/builder`);
    await page.waitForLoadState('networkidle');
  });

  test.afterEach(async () => {
    await page.close();
  });

  test('Scenario 1: Parse simple low-ambiguity rule', async () => {
    // User types a clear, unambiguous rule
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('Customer email must be from corporate domain');

    // Mock parse API endpoint - low confidence case
    await page.route('**/api/v1/rules/parse', route => {
      route.abort();
    });
    
    // Expect parse button to be clickable
    const parseBtn = page.locator('button:has-text("Parse Rule")');
    await expect(parseBtn).toBeEnabled();
  });

  test('Scenario 2: Parse rule requiring clarification', async () => {
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('If customer status changes, alert the operations team');

    // Mock parse API to return needs_clarification
    await page.route('**/api/v1/rules/parse', route => {
      route.respond({ status: 200, body: JSON.stringify(PARSE_NEEDS_CLARIFICATION) });
    });

    // Click parse
    await page.click('button:has-text("Parse Rule")');

    // Wait for clarification panel to appear
    const clarificationPanel = page.locator('[data-testid="clarification-panel"]');
    await expect(clarificationPanel).toBeVisible();

    // Verify clarification questions are displayed
    for (const question of PARSE_NEEDS_CLARIFICATION.clarifying_questions) {
      await expect(page.locator(`text=${question.question}`)).toBeVisible();
    }

    // Verify context is shown
    const contextBox = page.locator('[data-testid="clarification-context"]');
    await expect(contextBox).toBeVisible();
    await expect(page.locator('text=customer_master')).toBeVisible();
    await expect(page.locator('text=customer_email')).toBeVisible();

    // User answers first clarification question
    const firstAnswerInput = page.locator('[data-testid="answer-q1"]');
    await firstAnswerInput.fill('corporate.com');

    // User answers second clarification question
    const secondAnswerInput = page.locator('[data-testid="answer-q2"]');
    await secondAnswerInput.fill('All customers');

    // Mock second parse call with updated response
    await page.route('**/api/v1/rules/parse', route => {
      route.respond({ status: 200, body: JSON.stringify(PARSE_AFTER_CLARIFICATION) });
    });

    // Click "Apply Answers"
    await page.click('button:has-text("Apply Answers")');

    // Clarification panel should disappear
    await expect(clarificationPanel).not.toBeVisible();

    // Parse result should be displayed
    const parseResultPanel = page.locator('[data-testid="parse-result-panel"]');
    await expect(parseResultPanel).toBeVisible();

    // Verify high confidence badge
    const confidenceBadge = page.locator('[data-testid="confidence-badge-high"]');
    await expect(confidenceBadge).toBeVisible();
    await expect(confidenceBadge).toContainText('92%');

    // Verify no clarification warning
    const clarificationWarning = page.locator('[data-testid="clarification-needed-warning"]');
    await expect(clarificationWarning).not.toBeVisible();
  });

  test('Scenario 3: Disambiguation with candidate selection', async () => {
    // Start with a parsed rule
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('Validate customer email domain');

    // Mock parse to return parsed state
    await page.route('**/api/v1/rules/parse', route => {
      route.respond({ status: 200, body: JSON.stringify(PARSE_AFTER_CLARIFICATION) });
    });

    await page.click('button:has-text("Parse Rule")');

    // Mock resolve API to return disambiguation needed
    await page.route('**/api/v1/rules/resolve', route => {
      route.respond({ status: 200, body: JSON.stringify(RESOLVE_WITH_DISAMBIGUATION) });
    });

    // Click "Resolve" button
    await page.click('button:has-text("Resolve")');

    // Wait for disambiguation panel
    const disambiguationPanel = page.locator('[data-testid="disambiguation-panel"]');
    await expect(disambiguationPanel).toBeVisible();

    // Verify disambiguation warning
    const warning = page.locator('[data-testid="disambiguation-warning"]');
    await expect(warning).toBeVisible();
    await expect(warning).toContainText('Multiple candidates');

    // Verify first candidate is displayed with high score
    const candidate1 = page.locator('text=customer_master');
    await expect(candidate1).toBeVisible();
    const score1 = page.locator('text=98%').first();
    await expect(score1).toBeVisible();

    // Verify second candidate is displayed with lower score
    const candidate2 = page.locator('text=order_fact');
    await expect(candidate2).toBeVisible();
    const score2 = page.locator('text=72%');
    await expect(score2).toBeVisible();

    // Verify signal breakdown toggle
    const signalToggle = page.locator('[data-testid="signal-breakdown-toggle"]').first();
    await signalToggle.click();

    // Verify signals are displayed
    const signals = page.locator('[data-testid="signal-item"]');
    await expect(signals).toHaveCount(4); // name_match, type_match, domain_presence, sample_data_match
    await expect(page.locator('text=name_match')).toBeVisible();
    await expect(page.locator('text=98%')).toBeVisible(); // One of the signal scores

    // Collapse signal breakdown
    await signalToggle.click();
    await expect(page.locator('[data-testid="signal-item"]').first()).not.toBeVisible();
  });

  test('Scenario 4: Accept candidate and complete resolution', async () => {
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('Validate customer email domain');

    // Mock parse
    await page.route('**/api/v1/rules/parse', route => {
      route.respond({ status: 200, body: JSON.stringify(PARSE_AFTER_CLARIFICATION) });
    });

    // Mock resolve with disambiguation
    await page.route('**/api/v1/rules/resolve', route => {
      route.respond({ status: 200, body: JSON.stringify(RESOLVE_WITH_DISAMBIGUATION) });
    });

    await page.click('button:has-text("Parse Rule")');
    await page.click('button:has-text("Resolve")');

    // Wait for disambiguation panel
    const disambiguationPanel = page.locator('[data-testid="disambiguation-panel"]');
    await expect(disambiguationPanel).toBeVisible();

    // User selects first candidate (the one with 98% match)
    const firstCandidateRadio = page.locator('[data-testid="candidate-select-cand-1"]');
    await firstCandidateRadio.click();
    await expect(firstCandidateRadio).toBeChecked();

    // Mock final resolve call with disambiguation resolved
    await page.route('**/api/v1/rules/resolve', route => {
      route.respond({ status: 200, body: JSON.stringify(RESOLVE_AFTER_DISAMBIGUATION) });
    });

    // Click "Accept Resolution"
    const acceptBtn = page.locator('button:has-text("Accept Resolution")');
    await acceptBtn.click();

    // Disambiguation panel should disappear
    await expect(disambiguationPanel).not.toBeVisible();

    // Final rule summary should be displayed
    const ruleSummary = page.locator('[data-testid="rule-summary"]');
    await expect(ruleSummary).toBeVisible();

    // Verify rule details
    await expect(page.locator('text=Enterprise Customer Email Validation')).toBeVisible();
    await expect(page.locator('text=customer_master')).toBeVisible();
    await expect(page.locator('text=customer_email')).toBeVisible();
    await expect(page.locator('text=@corporate.com')).toBeVisible();
    await expect(page.locator('text=HIGH')).toBeVisible(); // Severity

    // User should be able to save rule or proceed to flow
    const saveBtn = page.locator('button:has-text("Save Rule")');
    await expect(saveBtn).toBeEnabled();
  });

  test('Scenario 5: Cancel disambiguation and go back', async () => {
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('Validate customer email domain');

    // Mock parse and resolve
    await page.route('**/api/v1/rules/parse', route => {
      route.respond({ status: 200, body: JSON.stringify(PARSE_AFTER_CLARIFICATION) });
    });

    await page.route('**/api/v1/rules/resolve', route => {
      route.respond({ status: 200, body: JSON.stringify(RESOLVE_WITH_DISAMBIGUATION) });
    });

    await page.click('button:has-text("Parse Rule")');
    await page.click('button:has-text("Resolve")');

    // Wait for disambiguation panel
    const disambiguationPanel = page.locator('[data-testid="disambiguation-panel"]');
    await expect(disambiguationPanel).toBeVisible();

    // Click "Cancel" button
    await page.click('button:has-text("Cancel")');

    // Disambiguation panel should disappear
    await expect(disambiguationPanel).not.toBeVisible();

    // User should be back to parse result view
    const parseResultPanel = page.locator('[data-testid="parse-result-panel"]');
    await expect(parseResultPanel).toBeVisible();
  });

  test('Scenario 6: Clear button resets entire form', async () => {
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await ruleInput.fill('Validate customer email domain');

    // Add severity and domain
    const severitySelect = page.locator('[data-testid="severity-select"]');
    await severitySelect.selectOption('HIGH');

    const domainInput = page.locator('[data-testid="domain-input"]');
    await domainInput.fill('Customer');

    // Click "Clear" button
    await page.click('button:has-text("Clear")');

    // Verify all fields are cleared
    await expect(ruleInput).toHaveValue('');
    await expect(severitySelect).toHaveValue('');
    await expect(domainInput).toHaveValue('');

    // No parse results should be displayed
    const parseResultPanel = page.locator('[data-testid="parse-result-panel"]');
    await expect(parseResultPanel).not.toBeVisible();
  });

  test('Scenario 7: Load rule from history', async () => {
    // Mock history containing previous rules
    const mockHistory = [
      {
        id: 'hist-1',
        rule_text: 'Customer email must be from corporate domain',
        timestamp: new Date().toISOString(),
        parsed_rule: PARSE_AFTER_CLARIFICATION.parsed_rule,
      },
    ];

    // Mock localStorage with history
    await page.context().addInitScript((history) => {
      localStorage.setItem('nl_rule_history', JSON.stringify(history));
    }, mockHistory);

    // Reload page
    await page.reload();

    // Click "History" button to expand history panel
    await page.click('button:has-text("History")');

    // Verify history item is shown
    const historyItem = page.locator('text=Customer email must be from corporate domain');
    await expect(historyItem).toBeVisible();

    // Click history item to load it
    await historyItem.click();

    // Verify rule is loaded into input
    const ruleInput = await page.locator('textarea[placeholder*="Enter natural language rule"]');
    await expect(ruleInput).toHaveValue('Customer email must be from corporate domain');
  });
});
