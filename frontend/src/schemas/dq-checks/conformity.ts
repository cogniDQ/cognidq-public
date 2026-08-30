/**
 * Conformity Dimension Schema — 6 subtypes
 * Registered on import.
 */
import { registerDimension } from './registry-store'
import type { DimensionSchema } from './types'

const schema: DimensionSchema = {
  dimension: 'conformity',
  defaultSubtype: 'standard',
  subtypes: [
    {
      subtype: 'standard',
      label: 'Standard Format',
      description: 'Values must conform to a well-known standard (email, phone, etc.)',
      requiresReferenceData: false,
      fields: [
        {
          key: 'standard_name',
          label: 'Standard',
          helpText: 'The standard to validate against',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'email',
          section: 'businessLogic',
          options: [
            { value: 'email', label: 'Email Address' },
            { value: 'phone', label: 'Phone Number' },
            { value: 'date_iso', label: 'Date (ISO 8601)' },
            { value: 'url', label: 'URL' },
            { value: 'uuid', label: 'UUID' },
            { value: 'ip_address', label: 'IP Address' },
            { value: 'credit_card', label: 'Credit Card Number' },
            { value: 'postal_code', label: 'Postal Code' },
            { value: 'ssn', label: 'SSN (US)' },
          ],
        },
      ],
      defaultConfig: () => ({ standard_name: 'email' }),
    },
    {
      subtype: 'regex',
      label: 'Regex Pattern',
      description: 'Values must match a custom regular expression',
      requiresReferenceData: false,
      fields: [
        {
          key: 'pattern',
          label: 'Regex Pattern',
          helpText: 'Custom regex that values must conform to',
          inputType: 'expression',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. ^[A-Z]{3}-[0-9]{4}$',
        },
      ],
      defaultConfig: () => ({ pattern: '' }),
    },
    {
      subtype: 'length',
      label: 'Length Constraint',
      description: 'String length must be within specified bounds',
      requiresReferenceData: false,
      fields: [
        {
          key: 'min_length',
          label: 'Minimum Length',
          helpText: 'Minimum allowed string length (leave empty for no min)',
          inputType: 'number',
          required: false,
          defaultValue: null,
          section: 'businessLogic',
          min: 0,
          placeholder: 'No minimum',
        },
        {
          key: 'max_length',
          label: 'Maximum Length',
          helpText: 'Maximum allowed string length (leave empty for no max)',
          inputType: 'number',
          required: false,
          defaultValue: null,
          section: 'businessLogic',
          min: 0,
          placeholder: 'No maximum',
        },
      ],
      defaultConfig: () => ({ min_length: null, max_length: null }),
    },
    {
      subtype: 'charset',
      label: 'Character Set',
      description: 'Values must only contain specified character sets',
      requiresReferenceData: false,
      fields: [
        {
          key: 'allowed_charset',
          label: 'Allowed Character Set',
          helpText: 'Which characters are permitted',
          inputType: 'dropdown',
          required: true,
          defaultValue: 'alphanumeric',
          section: 'businessLogic',
          options: [
            { value: 'alpha', label: 'Letters Only (A-Z, a-z)' },
            { value: 'numeric', label: 'Digits Only (0-9)' },
            { value: 'alphanumeric', label: 'Letters and Digits' },
            { value: 'ascii', label: 'ASCII (0-127)' },
            { value: 'printable', label: 'Printable Characters' },
            { value: 'custom', label: 'Custom Pattern' },
          ],
        },
        {
          key: 'custom_charset_pattern',
          label: 'Custom Pattern',
          helpText: 'Regex character class for allowed characters',
          inputType: 'expression',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. [A-Za-z0-9_\\-]',
          visibleWhen: (config) => config.allowed_charset === 'custom',
        },
      ],
      defaultConfig: () => ({
        allowed_charset: 'alphanumeric',
        custom_charset_pattern: '',
      }),
    },
    {
      subtype: 'case',
      label: 'Case Convention',
      description: 'Values must follow a specific casing convention',
      requiresReferenceData: false,
      fields: [
        {
          key: 'expected_case',
          label: 'Expected Case',
          helpText: 'The casing convention values must follow',
          inputType: 'radio',
          required: true,
          defaultValue: 'upper',
          section: 'businessLogic',
          options: [
            { value: 'upper', label: 'UPPER CASE' },
            { value: 'lower', label: 'lower case' },
            { value: 'title', label: 'Title Case' },
          ],
        },
      ],
      defaultConfig: () => ({ expected_case: 'upper' }),
    },
    {
      subtype: 'structural',
      label: 'Structural Pattern',
      description: 'Values must follow a structural template (e.g., XX-9999)',
      requiresReferenceData: false,
      fields: [
        {
          key: 'structural_pattern',
          label: 'Structural Pattern',
          helpText: 'A pattern using X (letter), 9 (digit), and literal characters',
          inputType: 'text',
          required: true,
          defaultValue: '',
          section: 'businessLogic',
          placeholder: 'e.g. XX-9999 or AAA-000-AAA',
        },
      ],
      defaultConfig: () => ({ structural_pattern: '' }),
    },
  ],
}

registerDimension(schema)
