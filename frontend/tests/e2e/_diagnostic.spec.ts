/**
 * Quick diagnostic — capture screenshots + DOM for each blocked step.
 * Not part of the regular test run; invoke explicitly:
 *   npx playwright test tests/e2e/_diagnostic.spec.ts --project=chromium
 */
import { test } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs/promises';
import { USERS, seedSessionAndGoto } from './helpers/auth';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUT = path.resolve(__dirname, '../../../qa/evidence/diagnostic');

const PAGES = [
  '/hub',
  '/hub/connections/new',
  '/hub/connections',
  '/hub/datasets',
  '/hub/glossary',
];

test('diagnostic — screenshots of blocked pages', async ({ page }) => {
  test.setTimeout(180_000);
  await fs.mkdir(OUT, { recursive: true });
  await seedSessionAndGoto(page, USERS.workspaceAdmin, '/hub');
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForURL(/\/hub\/ws\/[^/]+\/overview/, { timeout: 15_000 }).catch(() => {});
  const wsMatch = page.url().match(/\/ws\/([^/]+)/);
  const ws = wsMatch ? wsMatch[1] : '';
  // eslint-disable-next-line no-console
  console.log('discovered workspace_id =', ws);

  const pages = [
    '/hub',
    '/hub/connections/new',
    '/hub/connections',
    '/hub/datasets',
    '/hub/glossary',
    `/hub/ws/${ws}/glossary`,
    `/hub/ws/${ws}/datasets`,
    `/hub/ws/${ws}/nl-rule-builder`,
    `/hub/ws/${ws}/rules`,
    `/hub/ws/${ws}/issues`,
    `/hub/ws/${ws}/incidents`,
    `/hub/ws/${ws}/alerts`,
    `/hub/ws/${ws}/quality-reports`,
    `/hub/ws/${ws}/flows`,
    `/hub/ws/${ws}/flow-builder`,
    `/hub/ws/${ws}/executions`,
  ];

  for (const p of pages) {
    await page.goto(p, { waitUntil: 'domcontentloaded' });
    await page.waitForLoadState('networkidle').catch(() => {});
    await page.waitForTimeout(1200);
    const safe = p.replace(/[^a-z0-9]+/gi, '_');
    await page.screenshot({ path: path.join(OUT, `${safe}.png`), fullPage: true });
    const html = await page.content();
    await fs.writeFile(path.join(OUT, `${safe}.html`), html);
    const url = page.url();
    // eslint-disable-next-line no-console
    console.log(`captured ${p} -> ended on ${url}`);
  }
});
