/**
 * Consistency Dimension Schema — 6 subtypes
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'consistency',
  defaultSubtype: 'intra_record',
  subtypes: [
    {
      subtype: 'intra_record',
      label: 'Intra-Record Consistency',
      description: 'Validate relationships between fields within the same row',
      requiresReferenceData: false,
      fields: [
        {
          key: 'rule_expression',
          label: 'Consistency Rule',
          helpText: 'Expression defining the relationship between columns (e.g. start_date < end_date)',
          inputType: 'expression',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. start_date < end_date',
        },
      ],
      defaultConfig: () => ({ rule_expression: '' }),
    },
    {
      subtype: 'formula',
      label: 'Formula Consistency',
      description: 'Derived column must equal a formula of other columns',
      requiresReferenceData: false,
      fields: [
        {
          key: 'rule_expression',
          label: 'Formula Expression',
          helpText: 'Expression that derived column should equal (e.g. quantity * unit_price)',
          inputType: 'expression',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. quantity * unit_price',
        },
        {
          key: 'tolerance_type',
          label: 'Tolerance Type',
          helpText: 'How to handle floating-point comparison',
          inputType: 'dropdown',
          required: false,
          defaultValue: 'none',
          section: 'businessLogic',
          options: [
            { value: 'none', label: 'Exact Match' },
            { value: 'absolute', label: 'Absolute Tolerance' },
            { value: 'percentage', label: 'Percentage Tolerance' },
          ],
        },
        {
          key: 'tolerance_value',
          label: 'Tolerance Value',
          helpText: 'Allowed deviation from the expected value',
          inputType: 'number',
          required: false,
          defaultValue: 0,
          section: 'businessLogic',
          min: 0,
          visibleWhen: (config) => config.tolerance_type !== 'none',
        },
      ],
      defaultConfig: () => ({
        rule_expression: '',
        tolerance_type: 'none',
        tolerance_value: 0,
      }),
    },
    {
      subtype: 'temporal',
      label: 'Temporal Consistency',
      description: 'Validate temporal ordering between date/time columns',
      requiresReferenceData: false,
      fields: [
        {
          key: 'start_column',
          label: 'Start Column',
          helpText: 'Column containing the start date/time',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'end_column',
          label: 'End Column',
          helpText: 'Column containing the end date/time (must be >= start)',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({ start_column: '', end_column: '' }),
    },
    {
      subtype: 'inter_record',
      label: 'Inter-Record Consistency',
      description: 'Validate consistency across related rows within the same table',
      requiresReferenceData: false,
      fields: [
        {
          key: 'group_by_columns',
          label: 'Group By Columns',
          helpText: 'Columns defining related record groups',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'businessLogic',
        },
        {
          key: 'comparison_columns',
          label: 'Comparison Columns',
          helpText: 'Columns that should be consistent within each group',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({
        group_by_columns: [],
        comparison_columns: [],
      }),
    },
    {
      subtype: 'cross_table',
      label: 'Cross-Table Consistency',
      description: 'Validate consistency between this dataset and a reference dataset',
      requiresReferenceData: true,
      fields: [
        {
          key: 'comparison_columns',
          label: 'Comparison Columns',
          helpText: 'Columns to compare between source and reference datasets',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'referenceData',
        },
      ],
      defaultConfig: () => ({ comparison_columns: [] }),
    },
    {
      subtype: 'aggregation',
      label: 'Aggregation Consistency',
      description: 'Aggregate values must match expected totals or constraints',
      requiresReferenceData: false,
      fields: [
        {
          key: 'aggregate_function',
          label: 'Aggregate Function',
          helpText: 'Function to apply over the group',
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
          key: 'expected_column',
          label: 'Expected Total Column',
          helpText: 'Column containing the expected aggregate value',
          inputType: 'column-picker',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'group_by_columns',
          label: 'Group By Columns',
          helpText: 'Columns to group aggregation by',
          inputType: 'column-picker',
          required: false,
          defaultValue: [],
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({
        aggregate_function: 'SUM',
        expected_column: '',
        group_by_columns: [],
      }),
    },
  ],
}

registerDimension(schema)
