/**
 * E2E configuration helper.
 *
 * Every value used by the UI-driven Data Quality journey is sourced from
 * environment variables — no hard-coded credentials, fixture paths, or
 * rule shapes. Defaults are provided so a developer can run the spec
 * locally against the seeded QA stack without setting any env vars,
 * but every default can be overridden.
 *
 * The same set of variables is documented in
 * `documentation/qa/data_quality_ui_playbook.md` so a human can reproduce
 * the run by following the on-screen steps with the same inputs.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function env(name: string, fallback: string): string {
  const v = process.env[name];
  return v && v.length > 0 ? v : fallback;
}

function envOptional(name: string): string | undefined {
  const v = process.env[name];
  return v && v.length > 0 ? v : undefined;
}

const RUN_ID = env('E2E_RUN_ID', `${Date.now()}`).slice(-10);

export const E2E = {
  /** Persistent run identifier — used to prefix every generated name. */
  RUN_ID,

  /** Hosts. */
  apiBase: env('E2E_API_BASE', 'http://localhost:8000'),
  appBase: env('E2E_APP_BASE', 'http://localhost:5173'),

  /** Credentials of the user driving the journey. The default is the
   *  seeded platform administrator because Step 2 (tenant glossary write)
   *  requires platform_admin. Override with E2E_USER_EMAIL/E2E_USER_PASSWORD
   *  if you have a custom-seeded equivalent. */
  user: {
    email: env('E2E_USER_EMAIL', 'admin@example.com'),
    password: env('E2E_USER_PASSWORD', 'admin123'),
  },

  /** Optional: pin the workspace to use. When omitted, the spec uses
   *  whatever workspace the post-login redirect lands on. */
  workspaceId: envOptional('E2E_WORKSPACE_ID'),

  /** CSV fixture details. The file must already exist on the BACKEND host
   *  (or in the backend container) at `fixturePathInBackend`, because the
   *  CSV connector reads it server-side. The host-side path is only used
   *  if a UI file-upload step is added in the future. */
  fixture: {
    /** Absolute path the BACKEND can resolve to read the CSV. */
    pathInBackend: env('E2E_FIXTURE_BACKEND_PATH', '/tmp/dq_uploads/customers_with_quality_issues.csv'),
    /** Optional: host-side path (where the file lives on the developer's
     *  machine). Defaulted to qa/fixtures/. */
    pathOnHost: env(
      'E2E_FIXTURE_HOST_PATH',
      path.resolve(__dirname, '../../../../qa/fixtures/customers_with_quality_issues.csv'),
    ),
  },

  /** Names for created artefacts — fully run-id-scoped so consecutive runs
   *  don't collide. Override any of these via env if desired. */
  names: {
    glossaryTerm: env('E2E_GLOSSARY_TERM', `E2E Customer Email ${RUN_ID}`),
    glossaryTechnicalName: env('E2E_GLOSSARY_TECHNICAL', 'email'),
    glossaryDomain: env('E2E_GLOSSARY_DOMAIN', 'customer'),
    glossaryDefinition: env(
      'E2E_GLOSSARY_DEFINITION',
      'Customer email contact for marketing communications.',
    ),
    connection: env('E2E_CONNECTION_NAME', `e2e-csv-${RUN_ID}`),
    dataset: env('E2E_DATASET_NAME', `e2e_customers_${RUN_ID}`),
    rule: env('E2E_RULE_NAME', `E2E Email Not Null ${RUN_ID}`),
    alert: env('E2E_ALERT_NAME', `E2E Alert ${RUN_ID}`),
  },

  /** Rule the spec authors via the NL builder. The natural-language sentence
   *  is parsed by the backend; `targetColumn` is what the spec verifies the
   *  parser extracted. */
  rule: {
    nlText: env(
      'E2E_RULE_NL',
      'The email column must not be null',
    ),
    /** What we expect the parser to put in target_columns[0]. Used for
     *  assertions only — not as input. */
    expectedTargetColumn: env('E2E_RULE_EXPECTED_COLUMN', 'email'),
    expectedCategory: env('E2E_RULE_EXPECTED_CATEGORY', 'completeness'),
  },

  /** Alert the spec creates. */
  alert: {
    triggerType: env('E2E_ALERT_TRIGGER', 'execution_failed'),
  },
} as const;

/** Helper to build absolute API URLs from a path. */
export function apiUrl(p: string): string {
  return `${E2E.apiBase}${p.startsWith('/') ? '' : '/'}${p}`;
}
