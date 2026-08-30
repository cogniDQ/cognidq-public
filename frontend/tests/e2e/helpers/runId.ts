/**
 * Run-id helper — guarantees unique, deterministic-per-run names so that
 * the live E2E spec can re-create artefacts without colliding with previous runs.
 */
export function makeRunId(): string {
  // Derive from process env when CI sets one; otherwise from time.
  const seed = process.env.E2E_RUN_ID ?? `${Date.now()}`;
  return seed.slice(-10);
}

export const RUN_ID = makeRunId();

export const NAMES = {
  glossaryTerm: `E2E Customer Email ${RUN_ID}`,
  connection: `e2e-csv-${RUN_ID}`,
  dataset: `e2e_customers_${RUN_ID}`,
  ruleEmailNotNull: `E2E Customer Email Not Null ${RUN_ID}`,
  ruleEmailValid: `E2E Customer Email Valid ${RUN_ID}`,
  ruleIdUnique: `E2E Customer ID Unique ${RUN_ID}`,
  ruleAmountPositive: `E2E Order Amount Positive ${RUN_ID}`,
  ruleCountryValid: `E2E Country Code Valid ${RUN_ID}`,
  ruleBirthDateNotFuture: `E2E Birth Date Not Future ${RUN_ID}`,
  flow: `E2E Full Quality Flow ${RUN_ID}`,
};
