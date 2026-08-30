/**
 * Reconciliation Dimension Schema — 6 subtypes
 * 
 * The most complex dimension: ALL subtypes require two datasets.
 * The connected source node provides the "source" dataset; the
 * ReferenceDataSection provides the "target" dataset + join keys.
 * 
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'reconciliation',
  defaultSubtype: 'record_count',
  subtypes: [
    /* ── 1. Record Count ─────────────────────────────────────────── */
    {
      subtype: 'record_count',
      label: 'Record Count',
      description: 'Source and target must have the same number of records',
      requiresReferenceData: true,
      fields: [
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        source_filter: '',
        target_filter: '',
      }),
    },

    /* ── 2. One-to-One Matching ──────────────────────────────────── */
    {
      subtype: 'one_to_one',
      label: 'One-to-One Matching',
      description: 'Every source record has exactly one match in the target',
      requiresReferenceData: true,
      fields: [
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        source_filter: '',
        target_filter: '',
      }),
    },

    /* ── 3. Aggregate ────────────────────────────────────────────── */
    {
      subtype: 'aggregate',
      label: 'Aggregate Reconciliation',
      description: 'Aggregated values (SUM/COUNT/AVG) must match between datasets',
      requiresReferenceData: true,
      fields: [
        {
          key: 'aggregate_column',
          label: 'Aggregate Column',
          helpText: 'The column to aggregate',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'aggregate_function',
          label: 'Aggregate Function',
          helpText: 'How to aggregate values before comparing',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'SUM',
          section: 'businessLogic',
          options: [
            { value: 'SUM', label: 'SUM' },
            { value: 'COUNT', label: 'COUNT' },
            { value: 'AVG', label: 'AVG' },
            { value: 'MIN', label: 'MIN' },
            { value: 'MAX', label: 'MAX' },
          ],
        },
        {
          key: 'group_by_columns',
          label: 'Group By Columns',
          helpText: 'Optional columns to group reconciliation by',
          inputType: 'column-picker',
          required: false,
          defaultValue: [],
          section: 'businessLogic',
        },
        {
          key: 'tolerance_type',
          label: 'Tolerance Type',
          helpText: 'How to measure acceptable deviation',
          inputType: 'dropdown',
          required: false,
          defaultValue: 'none',
          section: 'businessLogic',
          options: [
            { value: 'none', label: 'Exact Match' },
            { value: 'absolute', label: 'Absolute (±N)' },
            { value: 'percentage', label: 'Percentage (±N%)' },
          ],
        },
        {
          key: 'tolerance_value',
          label: 'Tolerance Value',
          helpText: 'Maximum acceptable deviation',
          inputType: 'number',
          required: false,
          defaultValue: 0,
          section: 'businessLogic',
          min: 0,
          visibleWhen: (config) => config.tolerance_type !== 'none',
        },
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        aggregate_column: '',
        aggregate_function: 'SUM',
        group_by_columns: [],
        tolerance_type: 'none',
        tolerance_value: 0,
        source_filter: '',
        target_filter: '',
      }),
    },

    /* ── 4. Field-Level Comparison ───────────────────────────────── */
    {
      subtype: 'field_level',
      label: 'Field-Level Comparison',
      description: 'Individual field values must match between mapped records',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_columns',
          label: 'Comparison Columns',
          helpText: 'Columns to compare between source and target after joining',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'referenceData',
        },
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        compare_columns: [],
        source_filter: '',
        target_filter: '',
      }),
    },

    /* ── 5. Tolerance-Based Match ────────────────────────────────── */
    {
      subtype: 'tolerance',
      label: 'Tolerance-Based Match',
      description: 'Values can differ within a defined tolerance (absolute or percentage)',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_column',
          label: 'Compare Column',
          helpText: 'Column to compare between datasets',
          inputType: 'column-picker',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'tolerance_type',
          label: 'Tolerance Type',
          helpText: 'How to measure allowed deviation',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'absolute',
          section: 'businessLogic',
          options: [
            { value: 'absolute', label: 'Absolute (±N)' },
            { value: 'percentage', label: 'Percentage (±N%)' },
          ],
        },
        {
          key: 'tolerance_value',
          label: 'Tolerance Value',
          helpText: 'Maximum acceptable deviation',
          inputType: 'number',
          required: true,
          defaultValue: 0,
          section: 'businessLogic',
          min: 0,
        },
        {
          key: 'aggregate_function',
          label: 'Aggregate Function',
          helpText: 'Optional aggregation before comparison',
          inputType: 'dropdown',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          options: [
            { value: '', label: 'None' },
            { value: 'SUM', label: 'SUM' },
            { value: 'COUNT', label: 'COUNT' },
            { value: 'AVG', label: 'AVG' },
            { value: 'MIN', label: 'MIN' },
            { value: 'MAX', label: 'MAX' },
          ],
        },
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        compare_column: '',
        tolerance_type: 'absolute',
        tolerance_value: 0,
        aggregate_function: '',
        source_filter: '',
        target_filter: '',
      }),
    },

    /* ── 6. Missing & Extra Records ──────────────────────────────── */
    {
      subtype: 'missing_extra',
      label: 'Missing & Extra Records',
      description: 'Identify records present in source but missing from target, and vice versa',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_columns',
          label: 'Additional Compare Columns',
          helpText: 'Extra columns to compare for matched records',
          inputType: 'column-picker',
          required: false,
          defaultValue: [],
          section: 'referenceData',
        },
        {
          key: 'source_filter',
          label: 'Source Filter',
          helpText: 'Optional WHERE clause for the source dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
        {
          key: 'target_filter',
          label: 'Target Filter',
          helpText: 'Optional WHERE clause for the target dataset',
          inputType: 'expression',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: "e.g. status = 'active'",
        },
      ],
      defaultConfig: () => ({
        compare_columns: [],
        source_filter: '',
        target_filter: '',
      }),
    },
  ],
}

registerDimension(schema)
