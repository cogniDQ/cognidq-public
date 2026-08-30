/**
 * Completeness Dimension Schema — 7 subtypes
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'completeness',
  defaultSubtype: 'null',
  subtypes: [
    {
      subtype: 'null',
      label: 'NULL Check',
      description: 'Ensures values are not NULL',
      requiresReferenceData: false,
      fields: [
        {
          key: 'include_empty_strings',
          label: 'Include Empty Strings',
          helpText: 'Also treat empty/whitespace-only strings as missing',
          inputType: 'toggle',
          required: false,
          defaultValue: true,
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({ include_empty_strings: true }),
    },
    {
      subtype: 'empty',
      label: 'Empty String Check',
      description: 'Detects empty or whitespace-only values',
      requiresReferenceData: false,
      fields: [],
      defaultConfig: () => ({}),
    },
    {
      subtype: 'placeholder',
      label: 'Placeholder Detection',
      description: 'Flags placeholder/sentinel values (N/A, TBD, etc.)',
      requiresReferenceData: false,
      fields: [
        {
          key: 'placeholder_values',
          label: 'Placeholder Values',
          helpText: 'Values to treat as placeholders. Press Enter to add.',
          inputType: 'tag-input',
          required: true,
          defaultValue: ['N/A', 'TBD', 'unknown', 'null', '-'],
          section: 'businessLogic',
          placeholder: 'Add a placeholder value…',
        },
        {
          key: 'case_sensitive',
          label: 'Case Sensitive',
          helpText: 'Match placeholder values with exact case',
          inputType: 'toggle',
          required: false,
          defaultValue: false,
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({
        placeholder_values: ['N/A', 'TBD', 'unknown', 'null', '-'],
        case_sensitive: false,
      }),
    },
    {
      subtype: 'conditional',
      label: 'Conditional Completeness',
      description: 'Column must be filled only when a condition is met',
      requiresReferenceData: false,
      fields: [
        {
          key: 'condition_column',
          label: 'Condition Column',
          helpText: 'The column whose value triggers the completeness requirement',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'condition_operator',
          label: 'Operator',
          helpText: 'How to evaluate the condition column',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'equals',
          section: 'businessLogic',
          options: [
            { value: 'equals', label: 'Equals' },
            { value: 'not_equals', label: 'Not Equals' },
            { value: 'in', label: 'In List' },
            { value: 'not_null', label: 'Is Not NULL' },
            { value: 'is_null', label: 'Is NULL' },
          ],
        },
        {
          key: 'condition_value',
          label: 'Condition Value',
          helpText: 'Value to compare against (comma-separated for "In List")',
          inputType: 'text',
          required: false,
          defaultValue: '',
          section: 'businessLogic',
          visibleWhen: (config) => !['not_null', 'is_null'].includes(config.condition_operator as string),
        },
      ],
      defaultConfig: () => ({
        condition_column: '',
        condition_operator: 'equals',
        condition_value: '',
      }),
    },
    {
      subtype: 'multi_field',
      label: 'Multi-Field Completeness',
      description: 'Check completeness across multiple columns together',
      requiresReferenceData: false,
      fields: [
        {
          key: 'multi_field_mode',
          label: 'Mode',
          helpText: 'All: every column must be filled. Any: at least one must be filled.',
          inputType: 'radio',
          required: true,
          defaultValue: 'all',
          section: 'businessLogic',
          options: [
            { value: 'all', label: 'All columns must be filled' },
            { value: 'any', label: 'At least one column must be filled' },
          ],
        },
      ],
      defaultConfig: () => ({ multi_field_mode: 'all' }),
    },
    {
      subtype: 'population',
      label: 'Population Coverage',
      description: 'Measures how many rows have non-null values (threshold typically < 100%)',
      requiresReferenceData: false,
      fields: [],
      defaultConfig: () => ({}),
    },
    {
      subtype: 'group',
      label: 'Group-Level Completeness',
      description: 'Check completeness within groups defined by group-by columns',
      requiresReferenceData: false,
      fields: [
        {
          key: 'group_by_columns',
          label: 'Group By Columns',
          helpText: 'Columns to define groups for aggregated completeness',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({ group_by_columns: [] }),
    },
  ],
}

registerDimension(schema)
