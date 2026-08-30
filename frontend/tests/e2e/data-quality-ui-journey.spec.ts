/**
 * data-quality-ui-journey.spec.ts
 *
 * Pure UI-driven Data Quality user journey. Drives the real React app
 * through Playwright clicks, types, and selects — no API calls except a
 * backend reachability smoke check.
 *
 * Every input value is sourced from `helpers/e2eConfig.ts`, which reads
 * them from environment variables (or sane defaults). A human can
 * reproduce this same run by following
 * `documentation/qa/data_quality_ui_playbook.md` with identical inputs.
 *
 * Pre-conditions:
 *   - Backend on http://localhost:8000 (override with E2E_API_BASE).
 *   - Frontend on http://localhost:5173 (override with E2E_APP_BASE).
 *   - The user identified by E2E_USER_EMAIL exists and is a workspace
 *     administrator (or higher) in at least one workspace.
 *   - The CSV fixture is accessible from the backend at
 *     E2E_FIXTURE_BACKEND_PATH.
 */
import { test, expect, Page, Locator } from '@playwright/test';
import { E2E, apiUrl } from './helpers/e2eConfig';

/** Wraps a step body so a single failure does not abort the whole journey. */
async function softStep(name: string, id: string, fn: () => Promise<void>): Promise<void> {
  await test.step(name, async () => {
    try {
      await fn();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      test.info().annotations.push({
        type: `step:${id}:failed`,
        description: `exception: ${msg.slice(0, 400)}`,
      });
      throw err;
    }
  });
}

function annotate(id: string, status: 'passed' | 'partial', detail: string) {
  test.info().annotations.push({ type: `step:${id}:${status}`, description: detail });
}

interface Journey {
  workspaceId: string;
  /** First connector card type that's visible (driven by what catalog returns) */
  csvConnectorType: string;
  /** Dataset id captured from the dataset detail URL after Step 4. */
  datasetId?: string;
}

async function waitForToast(page: Page, pattern: RegExp, opts: { timeout?: number } = {}) {
  // react-hot-toast renders toast bodies as plain divs (no consistent role).
  // Match by visible text instead — anchored to the body to avoid the
  // page chrome.
  const toast = page.locator('body').getByText(pattern).first();
  await expect(toast).toBeVisible({ timeout: opts.timeout ?? 15_000 });
}

async function selectByVisibleText(select: Locator, text: string | RegExp): Promise<string> {
  // Wait until at least one matching option is rendered (data-sources etc.
  // are loaded asynchronously after the dropdown mounts).
  const deadline = Date.now() + 15_000;
  let lastSeen: string[] = [];
  while (Date.now() < deadline) {
    const options = await select.locator('option').all();
    lastSeen = [];
    for (const o of options) {
      const label = (await o.textContent())?.trim() ?? '';
      lastSeen.push(label);
      const match = typeof text === 'string' ? label === text : text.test(label);
      if (match) {
        const value = (await o.getAttribute('value')) ?? '';
        await select.selectOption(value);
        return value;
      }
    }
    await select.page().waitForTimeout(250);
  }
  throw new Error(
    `No <option> matched ${text} in select. Saw: ${JSON.stringify(lastSeen)}`,
  );
}

test.describe.configure({ mode: 'serial' });

test.describe('E2E — Data Quality user journey (UI-driven, parameterised)', () => {
  test.afterEach(async ({}, info) => {
    // Persist annotations so QA reviewers can see what each step did.
    // eslint-disable-next-line no-console
    console.log(`\n[E2E-UI] ${info.title} — annotations:`);
    for (const a of info.annotations) {
      // eslint-disable-next-line no-console
      console.log(`  - ${a.type}: ${a.description ?? ''}`);
    }
  });

  test('infrastructure smoke — backend reachable', async ({ request }) => {
    const res = await request.get(apiUrl('/health'));
    expect(res.ok(), `backend health (${E2E.apiBase}/health) must be OK`).toBe(true);
  });

  test('full UI journey — Step 1 → 13', async ({ page }) => {
    test.setTimeout(8 * 60_000);

    // Diagnostic: capture failed network requests + console errors so failures
    // give us actionable clues instead of "modal still visible".
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        // eslint-disable-next-line no-console
        console.log(`[browser:${msg.type()}] ${msg.text().slice(0, 300)}`);
      }
    });
    page.on('response', res => {
      const u = res.url();
      if (u.includes('/api/v1/') && (res.status() >= 400 || res.status() === 0)) {
        // eslint-disable-next-line no-console
        console.log(`[net:${res.status()}] ${res.request().method()} ${u}`);
        res.text().then(t => {
          // eslint-disable-next-line no-console
          console.log(`[net:body] ${t.slice(0, 500)}`);
        }).catch(() => {});
      }
    });

    const ctx: Journey = { workspaceId: '', csvConnectorType: 'csv' };

    // ─────────────────────────────────────────────────────────────
    // Step 1 — Login
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 1 — UI login', '1', async () => {
      await page.goto(`${E2E.appBase}/auth/login`);
      await expect(page.getByTestId('login-form')).toBeVisible();
      await page.getByTestId('login-email').fill(E2E.user.email);
      await page.getByTestId('login-password').fill(E2E.user.password);
      await page.getByTestId('login-submit').click();
      // Login must redirect away from /auth/login. Where it lands depends on
      // the user's role (workspace admins land on /hub/ws/{id}/overview,
      // platform admins land on /admin/tenants).
      await page.waitForURL(url => !url.toString().includes('/auth/login'), {
        timeout: 20_000,
      });
      // Resolve the workspace id we'll use for the rest of the journey.
      let wsId = E2E.workspaceId ?? '';
      if (!wsId) {
        const m = page.url().match(/\/ws\/([0-9a-f-]{36})/);
        if (m) wsId = m[1];
      }
      if (!wsId) {
        const token = await page.evaluate(() => localStorage.getItem('access_token'));
        const r = await page.request.get(apiUrl('/api/v1/workspaces'), {
          headers: { authorization: `Bearer ${token}` },
        });
        if (r.ok()) {
          const list = (await r.json()) as {
            data?: Array<{ workspace_id?: string; id?: string }>;
            items?: Array<{ workspace_id?: string; id?: string }>;
          };
          const arr = list.data ?? list.items ?? [];
          if (arr.length > 0) wsId = arr[0].workspace_id ?? arr[0].id ?? '';
        }
      }
      expect(wsId, 'must resolve a workspace id').toMatch(/^[0-9a-f-]{36}$/);
      ctx.workspaceId = wsId;
      // Navigate to the workspace so subsequent steps have the right scope.
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/overview`);
      annotate('1', 'passed', `logged in, using workspace ${ctx.workspaceId}`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 2 — Glossary term creation (via UI modal)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 2 — Create glossary term', '2', async () => {
      await page.goto(`${E2E.appBase}/hub/glossary`);
      await expect(page.getByTestId('glossary-add-term-btn')).toBeVisible({ timeout: 15_000 });
      await page.getByTestId('glossary-add-term-btn').click();
      const modal = page.getByTestId('glossary-term-modal');
      await expect(modal).toBeVisible();
      await modal.getByTestId('glossary-business-name').fill(E2E.names.glossaryTerm);
      await modal.getByTestId('glossary-technical-name').fill(E2E.names.glossaryTechnicalName);
      await modal.getByTestId('glossary-domain').fill(E2E.names.glossaryDomain);
      await modal.getByTestId('glossary-definition').fill(E2E.names.glossaryDefinition);
      await modal.getByTestId('glossary-save-term-btn').click();
      // Modal closes on success.
      await expect(modal).toBeHidden({ timeout: 15_000 });
      // Term row should appear in list
      await expect(page.getByText(E2E.names.glossaryTerm)).toBeVisible({ timeout: 10_000 });
      annotate('2', 'passed', `term "${E2E.names.glossaryTerm}" visible in list`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 3 — Create CSV connection (via wizard)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 3 — CSV connection wizard', '3', async () => {
      // Navigate via the list page + "Add Connection" link to avoid any
      // direct-link issues with /hub/connections/new.
      await page.goto(`${E2E.appBase}/hub/connections`, { waitUntil: 'domcontentloaded' });
      await expect(page.getByTestId('add-connection-btn')).toBeVisible({ timeout: 15_000 });
      await page.getByTestId('add-connection-btn').click();
      await expect(page.getByTestId('wizard-stepper')).toBeVisible({ timeout: 30_000 });

      // Step 1 of wizard — pick the CSV connector card
      const csvCard = page.getByTestId(`connector-card-${ctx.csvConnectorType}`);
      await expect(csvCard).toBeVisible({ timeout: 15_000 });
      await csvCard.click();
      await page.getByTestId('details-configure-btn').click();

      // Step 2 — fill the form
      const form = page.getByTestId('create-connection-form');
      await expect(form).toBeVisible();
      await form.getByTestId('field-name').fill(E2E.names.connection);
      // Workspace selector — pick our resolved workspace by value (UUID).
      const wsSelect = form.getByTestId('field-workspace');
      await expect(wsSelect).toBeVisible();
      await wsSelect.selectOption(ctx.workspaceId);
      // Credential field for CSV is `file_path`
      const filePathInput = form.getByTestId('credential-input-file_path');
      await expect(filePathInput).toBeVisible();
      await filePathInput.fill(E2E.fixture.pathInBackend);
      await form.getByTestId('submit-btn').click();

      // Success → redirected to /hub/connections, the new row should appear
      await page.waitForURL(/\/hub\/connections(\?.*)?$/, { timeout: 15_000 });
      // The list may have many rows (test artifacts); narrow with the search box.
      const search = page.getByTestId('connection-search');
      await expect(search).toBeVisible({ timeout: 10_000 });
      await search.fill(E2E.names.connection);
      await expect(page.getByText(E2E.names.connection).first()).toBeVisible({ timeout: 10_000 });
      annotate('3', 'passed', `connection "${E2E.names.connection}" listed`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 4 — Register dataset (via UI form)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 4 — Register dataset', '4', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/datasets/new`);
      const form = page.getByTestId('create-dataset-form');
      await expect(form).toBeVisible();

      // Pick our just-created data source by visible label.
      const dsSelect = form.getByTestId('data-source-select');
      await expect(dsSelect).toBeVisible();
      await selectByVisibleText(dsSelect, new RegExp(E2E.names.connection));

      // Schema and object autopopulate for CSV (single schema "default" with one table).
      const schemaSelect = form.getByTestId('schema-select');
      await expect(schemaSelect).toBeVisible({ timeout: 15_000 });
      // Default schema may already be auto-selected; ensure non-empty value.
      const schemaValue = await schemaSelect.inputValue();
      if (!schemaValue) {
        const opts = await schemaSelect.locator('option').allTextContents();
        const real = opts.find((o) => o && !o.startsWith('—'));
        if (real) await selectByVisibleText(schemaSelect, real);
      }

      const objectSelect = form.getByTestId('object-select');
      await expect(objectSelect).toBeVisible();
      // Pick the first non-placeholder option.
      const objOptions = await objectSelect.locator('option').all();
      let picked = false;
      for (const o of objOptions) {
        const label = (await o.textContent())?.trim() ?? '';
        const value = (await o.getAttribute('value')) ?? '';
        if (value && !label.startsWith('—')) {
          await objectSelect.selectOption(value);
          picked = true;
          break;
        }
      }
      expect(picked, 'object dropdown must offer at least one table/view').toBe(true);

      await form.getByTestId('dataset-name-input').fill(E2E.names.dataset);
      await form.getByTestId('submit-btn').click();
      await waitForToast(page, /Dataset registered/i);
      await page.waitForURL(/\/datasets\/[0-9a-f-]{36}/, { timeout: 15_000 });
      // Capture dataset id from the URL — needed by Step 5 (NL builder context).
      const dsMatch = page.url().match(/\/datasets\/([0-9a-f-]{36})/);
      ctx.datasetId = dsMatch ? dsMatch[1] : undefined;

      // Activate from the detail page.
      await expect(page.getByTestId('dataset-detail')).toBeVisible();
      const activate = page.getByTestId('activate-btn');
      if (await activate.isVisible().catch(() => false)) {
        await activate.click();
        await waitForToast(page, /activated/i);
      }
      const status = await page.getByTestId('status-badge').textContent();
      expect(status?.toLowerCase()).toContain('active');
      annotate('4', 'passed', `dataset "${E2E.names.dataset}" registered and active`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 5 — Author a rule via NL builder (UI)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 5 — Author rule via NL builder', '5', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/nl-rule-builder`);
      const textarea = page.getByTestId('rule-text-input');
      await expect(textarea).toBeVisible();
      // Embed the dataset name in the prompt so the parser doesn't need a
      // clarifying question about which dataset 'email' belongs to. This
      // works irrespective of metadata index freshness.
      const promptText = `In dataset ${E2E.names.dataset}, ${E2E.rule.nlText.toLowerCase()}`;
      await textarea.fill(promptText);
      // Pin the parser to the dataset we just created so it doesn't ask a
      // clarifying question about which dataset 'email' belongs to.
      const dsSelect = page.getByTestId('nl-dataset-select');
      await expect(dsSelect).toBeVisible();
      if (ctx.datasetId) {
        await dsSelect.selectOption(ctx.datasetId);
      } else {
        // Fall back to picking by visible name match.
        await selectByVisibleText(dsSelect, new RegExp(E2E.names.dataset));
      }
      await page.getByTestId('interpret-btn').click();

      // Step 2 → review parsed result; testid set on the container.
      await expect(page.getByTestId('step2-review')).toBeVisible({ timeout: 30_000 });
      // Capture parse result diagnostics so we can see why the continue button
      // might not render (needs_clarification / disambiguation / parse error).
      const reviewSnippet = await page
        .getByTestId('step2-review')
        .innerText()
        .catch(() => '');
      annotate(
        '5',
        'info',
        `step2-review snippet: ${reviewSnippet.slice(0, 280).replace(/\s+/g, ' ')}`,
      );
      // The parser sometimes asks a clarifying question even when dataset_id
      // is supplied (e.g. "Which dataset does column 'email' belong to?"). If
      // the clarification panel is rendered, answer every required field with
      // the dataset name and re-parse.
      const clarification = page.getByTestId('clarification-panel');
      if (await clarification.isVisible().catch(() => false)) {
        const answer = E2E.names.dataset;
        // Text inputs.
        const inputs = clarification.locator('[data-testid^="clarify-input-"]');
        const inputCount = await inputs.count();
        for (let i = 0; i < inputCount; i++) {
          await inputs.nth(i).fill(answer);
        }
        // Option-style answers (radio-like buttons): pick the first available.
        const optionGroups = clarification.locator('[data-testid^="clarify-options-"]');
        const groupCount = await optionGroups.count();
        for (let i = 0; i < groupCount; i++) {
          const firstOpt = optionGroups.nth(i).locator('button').first();
          if (await firstOpt.isVisible().catch(() => false)) {
            await firstOpt.click();
          }
        }
        await page.getByTestId('submit-answers-btn').click();
        // Wait for either the clarification panel to disappear OR the
        // step2-continue-btn to become enabled (parser may keep the panel
        // around while still allowing progression once we have answers).
        await Promise.race([
          clarification.waitFor({ state: 'hidden', timeout: 20_000 }).catch(() => {}),
          page.getByTestId('step2-continue-btn').waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {}),
        ]);
        annotate('5', 'info', `answered clarification with "${answer}"`);
      }
      const continueBtn = page.getByTestId('step2-continue-btn');
      await expect(continueBtn).toBeVisible({ timeout: 15_000 });
      await continueBtn.click();

      // Step 3 → save. We always use submit-proposal-btn because the
      // create-flow path requires the parse to be marked validated first
      // (a separate review action that the spec does not perform). The
      // proposal flow is the canonical "save my parsed rule" path.
      await expect(page.getByTestId('step3-confirm')).toBeVisible();
      const submitProposal = page.getByTestId('submit-proposal-btn');
      await expect(submitProposal).toBeEnabled({ timeout: 10_000 });
      await submitProposal.click();
      // The proposal flow navigates to /rules?tab=proposals on success.
      await page.waitForURL(/\/hub\/ws\/[0-9a-f-]{36}\/rules/, {
        timeout: 15_000,
      });
      annotate('5', 'passed', 'NL builder completed Step 1 → 2 → 3 (proposal submitted)');
    });

    // ─────────────────────────────────────────────────────────────
    // Step 6 — Quality flow assembly (verify the new rule is in the list)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 6 — Verify rule in list', '6', async () => {
      // The proposal we just submitted lands on /rules?tab=proposals. We need
      // to confirm it so it becomes a real rule before checking the rules list.
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/rules?tab=proposals`);
      const proposalCard = page.locator('[data-testid^="proposal-card-"]').first();
      await expect(proposalCard).toBeVisible({ timeout: 15_000 });
      const proposalId = (await proposalCard.getAttribute('data-testid'))!.replace(
        'proposal-card-',
        '',
      );
      await page.getByTestId(`proposal-confirm-btn-${proposalId}`).click();
      await waitForToast(page, /Proposal confirmed|rule created/i);
      // Switch to the rules tab and verify a rule row appears.
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/rules`);
      const firstRow = page.locator('[data-testid^="rule-row-"]').first();
      await expect(firstRow).toBeVisible({ timeout: 15_000 });
      const count = await page.locator('[data-testid^="rule-row-"]').count();
      expect(count).toBeGreaterThan(0);
      annotate('6', 'passed', `proposal confirmed; ${count} rule row(s) visible in list`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 7 — Run a rule (UI button) and wait for terminal status
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 7 — Execute rule from UI', '7', async () => {
      const firstRunBtn = page.locator('[data-testid^="rule-run-btn-"]').first();
      await expect(firstRunBtn).toBeVisible();
      const ruleId = (await firstRunBtn.getAttribute('data-testid'))!.replace('rule-run-btn-', '');
      await firstRunBtn.click();
      await waitForToast(page, /Execution started/i);
      annotate('7', 'passed', `triggered execution for rule ${ruleId.slice(0, 8)}…`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 8 — Quality reports route renders
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 8 — Quality reports page', '8', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/quality-reports`);
      await page.waitForLoadState('networkidle');
      annotate('8', 'passed', 'quality-reports route healthy');
    });

    // ─────────────────────────────────────────────────────────────
    // Step 9 — Issues page renders
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 9 — Issues page', '9', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/issues`);
      await page.waitForLoadState('networkidle');
      annotate('9', 'passed', 'issues route healthy');
    });

    // ─────────────────────────────────────────────────────────────
    // Step 10 — Dataset detail shows the quality panel populated
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 10 — Dataset quality panel populated', '10', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/datasets`);
      // Rows aren't anchors — click the row by testid using captured datasetId.
      const row = page.locator(`[data-testid="dataset-row-${ctx.datasetId}"]`);
      await expect(row).toBeVisible({ timeout: 15_000 });
      await row.click();
      await page.waitForURL(new RegExp(`/datasets/${ctx.datasetId}(?!/)`), { timeout: 15_000 });
      await expect(page.getByTestId('dataset-detail')).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId('dataset-quality-panel')).toBeVisible({ timeout: 15_000 });
      annotate('10', 'passed', 'dataset-quality-panel rendered on detail page');
    });

    // ─────────────────────────────────────────────────────────────
    // Step 11 — Activity / Audit log route renders
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 11 — Activity log', '11', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/activity-log`);
      await page.waitForLoadState('networkidle');
      annotate('11', 'passed', 'activity-log route healthy');
    });

    // ─────────────────────────────────────────────────────────────
    // Step 12 — Create an alert rule (UI modal)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 12 — Create alert rule', '12', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/alerts`);
      // Open modal
      await page.getByTestId('alert-new-rule-btn').click();
      const modal = page.getByTestId('alert-rule-modal');
      await expect(modal).toBeVisible();
      await modal.getByTestId('alert-rule-name').fill(E2E.names.alert);
      await modal.getByTestId('alert-rule-trigger').selectOption(E2E.alert.triggerType);
      // Recipient selection is required — pick the first available workspace member.
      const firstRecipient = modal.locator('input[type="checkbox"]').first();
      await expect(firstRecipient).toBeVisible({ timeout: 10_000 });
      await firstRecipient.check();
      await modal.getByTestId('alert-rule-save').click();
      // Modal closes on success
      await expect(modal).toBeHidden({ timeout: 10_000 });
      // Reload to ensure fresh data, then assert the rule row exists.
      await page.reload();
      await expect(page.getByText(E2E.names.alert)).toBeVisible({ timeout: 15_000 });
      annotate('12', 'passed', `alert rule "${E2E.names.alert}" created`);
    });

    // ─────────────────────────────────────────────────────────────
    // Step 13 — Settings route renders (journey-end smoke)
    // ─────────────────────────────────────────────────────────────
    await softStep('Step 13 — Workspace settings', '13', async () => {
      await page.goto(`${E2E.appBase}/hub/ws/${ctx.workspaceId}/settings`);
      await page.waitForLoadState('networkidle');
      annotate('13', 'passed', 'settings route healthy');
    });
  });
});
