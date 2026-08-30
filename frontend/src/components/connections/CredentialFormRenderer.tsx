/**
 * F-CONN-UX — Credential Form Renderer
 *
 * Renders a controlled form whose fields are driven entirely by a
 * `CredentialField[]` schema returned by `/api/v1/connectors/{type}`.
 * Eliminates per-connector branches in the wizard.
 *
 * The renderer is a *controlled* component: the parent owns the value map
 * and calls `onChange(name, value)` for each edit.
 */
import { ChangeEvent } from 'react';
import { CredentialField } from '../../services/connectorCatalogService';

export interface CredentialFormRendererProps {
  fields: CredentialField[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
  errors?: Record<string, string>;
  disabled?: boolean;
}

export default function CredentialFormRenderer({
  fields,
  values,
  onChange,
  errors,
  disabled,
}: CredentialFormRendererProps) {
  return (
    <div className="space-y-3" data-testid="credential-form">
      {fields.map((field) => (
        <FieldRow
          key={field.name}
          field={field}
          value={values[field.name] ?? field.default ?? ''}
          onChange={onChange}
          error={errors?.[field.name]}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

interface FieldRowProps {
  field: CredentialField;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  error?: string;
  disabled?: boolean;
}

function FieldRow({ field, value, onChange, error, disabled }: FieldRowProps) {
  const id = `cred-field-${field.name}`;
  const inputClass = `input w-full${error ? ' border-red-600 focus:ring-red-500' : ''}${disabled ? ' opacity-50 cursor-not-allowed' : ''}`;
  const textareaClass = `textarea w-full${error ? ' border-red-600 focus:ring-red-500' : ''}${disabled ? ' opacity-50 cursor-not-allowed' : ''}`;

  function handleText(e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    onChange(field.name, e.target.value);
  }

  return (
    <div data-testid={`credential-row-${field.name}`}>
      <label htmlFor={id} className="block text-xs font-medium text-gray-400 mb-1.5">
        {field.label}
        {field.required && <span className="ml-1 text-red-400">*</span>}
      </label>

      {field.type === 'select' ? (
        <select
          id={id}
          value={String(value ?? '')}
          onChange={handleText}
          disabled={disabled}
          className={inputClass}
          data-testid={`credential-input-${field.name}`}
        >
          <option value="">— select —</option>
          {(field.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : field.type === 'boolean' ? (
        <label className="inline-flex items-center gap-2 text-sm text-gray-300">
          <input
            id={id}
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(field.name, e.target.checked)}
            disabled={disabled}
            className="h-4 w-4 rounded border-dark-600 bg-dark-800 text-primary-600 focus:ring-primary-500 disabled:opacity-50"
            data-testid={`credential-input-${field.name}`}
          />
          {field.placeholder ?? 'Enabled'}
        </label>
      ) : field.type === 'json' ? (
        <textarea
          id={id}
          rows={4}
          value={String(value ?? '')}
          onChange={handleText}
          disabled={disabled}
          placeholder={field.placeholder}
          className={textareaClass + ' font-mono text-xs'}
          data-testid={`credential-input-${field.name}`}
        />
      ) : field.type === 'multiline' ? (
        <textarea
          id={id}
          rows={4}
          value={String(value ?? '')}
          onChange={handleText}
          disabled={disabled}
          placeholder={field.placeholder}
          className={textareaClass}
          data-testid={`credential-input-${field.name}`}
        />
      ) : (
        <input
          id={id}
          type={mapInputType(field.type)}
          value={String(value ?? '')}
          onChange={(e) =>
            onChange(
              field.name,
              field.type === 'number'
                ? e.target.value === ''
                  ? ''
                  : Number(e.target.value)
                : e.target.value,
            )
          }
          disabled={disabled}
          placeholder={field.placeholder}
          autoComplete={field.type === 'secret' ? 'new-password' : 'off'}
          className={inputClass}
          data-testid={`credential-input-${field.name}`}
        />
      )}

      {field.help_text && (
        <p className="mt-1 text-[11px] text-gray-500">{field.help_text}</p>
      )}
      {error && (
        <p
          className="mt-1 text-[11px] text-red-400"
          data-testid={`credential-error-${field.name}`}
        >
          {error}
        </p>
      )}
    </div>
  );
}

function mapInputType(t: CredentialField['type']): string {
  switch (t) {
    case 'secret':
      return 'password';
    case 'number':
      return 'number';
    case 'string':
    default:
      return 'text';
  }
}

/**
 * Validate a credential value map against a schema. Returns a map of
 * `{ field_name: error_message }` for any failures. Empty map means valid.
 *
 * Currently only checks `required` — type checks happen server-side via the
 * connector's `validate_config()`.
 */
export function validateCredentials(
  fields: CredentialField[],
  values: Record<string, unknown>,
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const f of fields) {
    if (!f.required) continue;
    const v = values[f.name];
    if (v === undefined || v === null || v === '') {
      errors[f.name] = `${f.label} is required`;
    }
  }
  return errors;
}
