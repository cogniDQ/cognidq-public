/**
 * F15 — Frontend lint config.
 *
 * The primary intent here is to prevent new code from regressing onto the
 * legacy `/workspaces/{id}/...` route family. All tenant-aware navigation
 * MUST go through `useTenantScopedPath().wsPath(...)` so the URL carries
 * both the tenant and workspace ids.
 *
 * Legacy pages that still reference the old route shape are listed in the
 * `overrides` block below as known debt. New offenders will fail lint.
 */

/** @type {import('eslint').Linter.Config} */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  ignorePatterns: [
    'dist',
    'node_modules',
    'dashboards',
    '.eslintrc.cjs',
    'playwright.config.ts',
    'vite.config.ts',
    'tests/**', // Playwright specs use their own conventions.
  ],
  plugins: ['react-refresh'],
  settings: { react: { version: '18' } },
  rules: {
    // Dev-only Fast Refresh hint; several pages legitimately co-export
    // helpers. Off for now, tighten over time.
    'react-refresh/only-export-components': 'off',

    // Deferred for this existing codebase; tighten over time (lint debt).
    // react-hooks/rules-of-hooks stays an error (real correctness guard);
    // exhaustive-deps is downgraded because mechanically adding deps to the
    // existing hooks risks changing runtime behavior. Revisit per-file.
    'react-hooks/exhaustive-deps': 'off',

    // F15 — Ban legacy tenant-less route literals in JSX `to=` attributes.
    // Every navigation must go through `wsPath()` so URLs carry tenant id.
    'no-restricted-syntax': [
      'error',
      {
        selector:
          "JSXAttribute[name.name='to'] Literal[value=/^\\/workspaces\\//]",
        message:
          'Legacy /workspaces/... route in <Link to=...>. Use useTenantScopedPath().wsPath() instead.',
      },
      {
        selector:
          "JSXAttribute[name.name='to'] TemplateLiteral > TemplateElement[value.raw=/^\\/workspaces\\//]",
        message:
          'Legacy /workspaces/${...} route in <Link to=...>. Use useTenantScopedPath().wsPath() instead.',
      },
      // Same ban for programmatic navigation.
      {
        selector:
          "CallExpression[callee.name='navigate'] Literal[value=/^\\/workspaces\\//]",
        message:
          'Legacy /workspaces/... route in navigate(). Use useTenantScopedPath().wsPath() instead.',
      },
      {
        selector:
          "CallExpression[callee.name='navigate'] TemplateLiteral > TemplateElement[value.raw=/^\\/workspaces\\//]",
        message:
          'Legacy /workspaces/${...} route in navigate(). Use useTenantScopedPath().wsPath() instead.',
      },
    ],

    // Sensible defaults that match the rest of the codebase.
    '@typescript-eslint/no-unused-vars': [
      'warn',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
    ],
    '@typescript-eslint/no-explicit-any': 'off',
    '@typescript-eslint/no-empty-function': 'off',
    'no-empty': ['warn', { allowEmptyCatch: true }],
    'prefer-const': 'warn',
  },
  overrides: [
    {
      // Known-debt: pages still using the legacy route shape. New code MUST
      // not be added here; instead migrate the file to wsPath() and remove
      // it from this list. Tracked under F15-followup.
      files: [
        'src/App.tsx',
        'src/pages/workspaces/WorkspaceDetailPage.tsx',
        'src/pages/workspaces/IssuesPage.tsx',
        'src/pages/workspaces/IssueDetailPage.tsx',
        'src/pages/datasets/CreateDatasetPage.tsx',
        'src/pages/datasets/EditDatasetPage.tsx',
        'src/pages/data-sources/CreateDataSourcePage.tsx',
        'src/pages/data-sources/EditDataSourcePage.tsx',
        'src/pages/data-sources/DataSourceListPage.tsx',
        'src/pages/data-sources/DataSourceDetailPage.tsx',
        'src/components/dashboards/AdoptionValueDashboard.tsx',
        'src/components/issues/IssueCard.tsx',
        'src/components/__tests__/**',
      ],
      rules: { 'no-restricted-syntax': 'off' },
    },
    {
      // Tests are allowed to construct any URL.
      files: ['**/*.test.ts', '**/*.test.tsx', 'src/**/__tests__/**'],
      rules: {
        'no-restricted-syntax': 'off',
        '@typescript-eslint/no-unused-vars': 'off',
      },
    },
  ],
};
