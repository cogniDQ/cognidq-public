/**
 * Accuracy Dimension Schema — 5 subtypes
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'accuracy',
  defaultSubtype: 'reference_comparison',
  subtypes: [
    {
      subtype: 'reference_comparison',
      label: 'Reference Comparison',
      description: 'Compare values against a trusted reference dataset',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_columns',
          label: 'Comparison Columns',
          helpText: 'Columns to compare between source and reference',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'referenceData',
        },
      ],
      defaultConfig: () => ({ compare_columns: [] }),
    },
    {
      subtype: 'trusted_source',
      label: 'Trusted Source Match',
      description: 'Values must match a master/golden record dataset',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_columns',
          label: 'Columns to Verify',
          helpText: 'Columns to validate against the trusted source',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'referenceData',
        },
        {
          key: 'match_type',
          label: 'Match Type',
          helpText: 'How to compare values',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'exact',
          section: 'businessLogic',
          options: [
            { value: 'exact', label: 'Exact Match' },
            { value: 'case_insensitive', label: 'Case Insensitive' },
            { value: 'trimmed', label: 'Trimmed (ignore whitespace)' },
          ],
        },
      ],
      defaultConfig: () => ({
        compare_columns: [],
        match_type: 'exact',
      }),
    },
    {
      subtype: 'tolerated_deviation',
      label: 'Tolerated Deviation',
      description: 'Values may deviate from reference within a tolerance',
      requiresReferenceData: true,
      fields: [
        {
          key: 'compare_column',
          label: 'Compare Column',
          helpText: 'Column to compare',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'referenceData',
        },
        {
          key: 'tolerance_type',
          label: 'Tolerance Type',
          helpText: 'How to measure permitted deviation',
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
          helpText: 'Maximum permitted deviation',
          inputType: 'number',
          required: true,
          defaultValue: 0,
          section: 'businessLogic',
          min: 0,
        },
      ],
      defaultConfig: () => ({
        compare_column: '',
        tolerance_type: 'absolute',
        tolerance_value: 0,
      }),
    },
    {
      subtype: 'statistical',
      label: 'Statistical Outlier',
      description: 'Detect outliers using statistical methods',
      requiresReferenceData: false,
      fields: [
        {
          key: 'method',
          label: 'Detection Method',
          helpText: 'Statistical method for outlier detection',
          inputType: 'radio',
          required: true,
          defaultValue: 'z_score',
          section: 'businessLogic',
          options: [
            { value: 'z_score', label: 'Z-Score' },
            { value: 'iqr', label: 'IQR (Interquartile Range)' },
          ],
        },
        {
          key: 'outlier_threshold',
          label: 'Outlier Threshold',
          helpText: 'Z-Score or IQR multiplier for outlier boundary',
          inputType: 'number',
          required: true,
          defaultValue: 3,
          section: 'businessLogic',
          min: 0,
        },
      ],
      defaultConfig: () => ({
        method: 'z_score',
        outlier_threshold: 3,
      }),
    },
    {
      subtype: 'derived_value',
      label: 'Derived Value Check',
      description: 'A column value must equal a formula applied to other columns',
      requiresReferenceData: false,
      fields: [
        {
          key: 'formula',
          label: 'Formula',
          helpText: 'Expression that should produce the expected value',
          inputType: 'expression',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. price * quantity * (1 - discount)',
        },
        {
          key: 'tolerance_type',
          label: 'Tolerance Type',
          helpText: 'How to handle floating-point differences',
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
          helpText: 'Maximum acceptable deviation',
          inputType: 'number',
          required: false,
          defaultValue: 0,
          section: 'businessLogic',
          min: 0,
          visibleWhen: (config) => config.tolerance_type !== 'none',
        },
      ],
      defaultConfig: () => ({
        formula: '',
        tolerance_type: 'none',
        tolerance_value: 0,
      }),
    },
  ],
}

registerDimension(schema)
