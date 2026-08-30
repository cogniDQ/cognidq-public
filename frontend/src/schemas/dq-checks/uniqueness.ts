/**
 * Uniqueness Dimension Schema — 6 subtypes
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'uniqueness',
  defaultSubtype: 'exact',
  subtypes: [
    {
      subtype: 'exact',
      label: 'Exact Uniqueness',
      description: 'No duplicate values in the selected columns',
      requiresReferenceData: false,
      fields: [],
      defaultConfig: () => ({}),
    },
    {
      subtype: 'composite',
      label: 'Composite Key',
      description: 'Unique combination of multiple columns',
      requiresReferenceData: false,
      fields: [],
      defaultConfig: () => ({}),
    },
    {
      subtype: 'scoped',
      label: 'Scoped Uniqueness',
      description: 'Unique within groups defined by scope columns',
      requiresReferenceData: false,
      fields: [
        {
          key: 'scope_columns',
          label: 'Scope Columns',
          helpText: 'Columns that define the scope within which uniqueness is checked',
          inputType: 'column-picker',
          required: true,
          defaultValue: [],
          section: 'businessLogic',
        },
      ],
      defaultConfig: () => ({ scope_columns: [] }),
    },
    {
      subtype: 'cross_dataset',
      label: 'Cross-Dataset Uniqueness',
      description: 'Values must be unique across both this and a reference dataset',
      requiresReferenceData: true,
      fields: [
        {
          key: 'cross_dataset_column',
          label: 'Reference Column',
          helpText: 'Column in the reference dataset to check against',
          inputType: 'text',
          required: true,
          defaultValue: '',
          section: 'referenceData',
        },
      ],
      defaultConfig: () => ({ cross_dataset_column: '' }),
    },
    {
      subtype: 'fuzzy',
      label: 'Fuzzy Duplicate Detection',
      description: 'Detect near-duplicates using similarity algorithms',
      requiresReferenceData: false,
      fields: [
        {
          key: 'fuzzy_algorithm',
          label: 'Algorithm',
          helpText: 'Similarity algorithm to use for fuzzy matching',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'levenshtein',
          section: 'businessLogic',
          options: [
            { value: 'levenshtein', label: 'Levenshtein Distance' },
            { value: 'jaro_winkler', label: 'Jaro-Winkler' },
            { value: 'soundex', label: 'Soundex' },
            { value: 'ngram', label: 'N-Gram Similarity' },
          ],
        },
        {
          key: 'fuzzy_threshold',
          label: 'Similarity Threshold',
          helpText: 'Minimum similarity score to consider as duplicate (0–1)',
          inputType: 'number-slider',
          required: true,
          defaultValue: 0.85,
          section: 'businessLogic',
          min: 0,
          max: 1,
        },
      ],
      defaultConfig: () => ({
        fuzzy_algorithm: 'levenshtein',
        fuzzy_threshold: 0.85,
      }),
    },
    {
      subtype: 'temporal',
      label: 'Temporal Uniqueness',
      description: 'Unique within a time window',
      requiresReferenceData: false,
      fields: [
        {
          key: 'temporal_column',
          label: 'Timestamp Column',
          helpText: 'Column containing timestamps for temporal scoping',
          inputType: 'column-picker',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
        },
        {
          key: 'temporal_window_value',
          label: 'Time Window',
          helpText: 'Duration of the uniqueness window',
          inputType: 'duration',
          required: true,
          defaultValue: 24,
          section: 'businessLogic',
        },
        {
          key: 'temporal_window_unit',
          label: 'Window Unit',
          helpText: 'Unit for the time window',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'hours',
          section: 'businessLogic',
          options: [
            { value: 'minutes', label: 'Minutes' },
            { value: 'hours', label: 'Hours' },
            { value: 'days', label: 'Days' },
            { value: 'weeks', label: 'Weeks' },
          ],
        },
      ],
      defaultConfig: () => ({
        temporal_column: '',
        temporal_window_value: 24,
        temporal_window_unit: 'hours',
      }),
    },
  ],
}

registerDimension(schema)
