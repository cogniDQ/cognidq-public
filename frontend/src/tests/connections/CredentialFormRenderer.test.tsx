/**
 * F-CONN-UX — CredentialFormRenderer component tests.
 *
 * Coverage:
 *   1. Renders one input per schema field.
 *   2. Required marker is rendered for required fields.
 *   3. onChange fires with correct (name, value) for text/number/boolean/select.
 *   4. validateCredentials() flags missing required fields.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import CredentialFormRenderer, {
  validateCredentials,
} from '@/components/connections/CredentialFormRenderer';
import type { CredentialField } from '@/services/connectorCatalogService';

const FIELDS: CredentialField[] = [
  {
    name: 'host',
    type: 'string',
    label: 'Host',
    required: true,
    placeholder: 'db.example.com',
  },
  {
    name: 'port',
    type: 'number',
    label: 'Port',
    required: true,
    default: 5432,
  },
  {
    name: 'use_ssl',
    type: 'boolean',
    label: 'Use SSL',
    required: false,
    default: false,
  },
  {
    name: 'mode',
    type: 'select',
    label: 'Mode',
    required: true,
    options: ['read_only', 'read_write'],
  },
  {
    name: 'password',
    type: 'secret',
    label: 'Password',
    required: true,
  },
];

describe('CredentialFormRenderer', () => {
  it('renders one row per schema field with required markers', () => {
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={() => {}} />,
    );
    for (const f of FIELDS) {
      expect(screen.getByTestId(`credential-row-${f.name}`)).toBeInTheDocument();
    }
    expect(screen.getByLabelText(/Host/)).toBeInTheDocument();
    // Required asterisk present for required fields
    const hostLabel = screen.getByText('Host').parentElement;
    expect(hostLabel?.textContent).toContain('*');
  });

  it('emits onChange with string value for text inputs', () => {
    const onChange = vi.fn();
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={onChange} />,
    );
    fireEvent.change(screen.getByTestId('credential-input-host'), {
      target: { value: 'db.local' },
    });
    expect(onChange).toHaveBeenCalledWith('host', 'db.local');
  });

  it('emits onChange with number value for port inputs', () => {
    const onChange = vi.fn();
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={onChange} />,
    );
    fireEvent.change(screen.getByTestId('credential-input-port'), {
      target: { value: '6543' },
    });
    expect(onChange).toHaveBeenCalledWith('port', 6543);
  });

  it('emits onChange with boolean for boolean inputs', () => {
    const onChange = vi.fn();
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={onChange} />,
    );
    fireEvent.click(screen.getByTestId('credential-input-use_ssl'));
    expect(onChange).toHaveBeenCalledWith('use_ssl', true);
  });

  it('emits onChange with selected value for select inputs', () => {
    const onChange = vi.fn();
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={onChange} />,
    );
    fireEvent.change(screen.getByTestId('credential-input-mode'), {
      target: { value: 'read_write' },
    });
    expect(onChange).toHaveBeenCalledWith('mode', 'read_write');
  });

  it('renders password type with type=password', () => {
    render(
      <CredentialFormRenderer fields={FIELDS} values={{}} onChange={() => {}} />,
    );
    const pw = screen.getByTestId('credential-input-password') as HTMLInputElement;
    expect(pw.type).toBe('password');
  });

  it('shows error message when errors prop populated', () => {
    render(
      <CredentialFormRenderer
        fields={FIELDS}
        values={{}}
        onChange={() => {}}
        errors={{ host: 'Host is required' }}
      />,
    );
    expect(screen.getByTestId('credential-error-host')).toHaveTextContent(
      'Host is required',
    );
  });
});

describe('validateCredentials', () => {
  it('flags missing required fields', () => {
    const errors = validateCredentials(FIELDS, { port: 5432 });
    expect(errors.host).toContain('required');
    expect(errors.mode).toContain('required');
    expect(errors.password).toContain('required');
    expect(errors.port).toBeUndefined();
    expect(errors.use_ssl).toBeUndefined();
  });

  it('returns empty object when all required fields present', () => {
    const errors = validateCredentials(FIELDS, {
      host: 'h',
      port: 5432,
      mode: 'read_only',
      password: 'p',
    });
    expect(errors).toEqual({});
  });

  it('treats empty string as missing', () => {
    const errors = validateCredentials(FIELDS, {
      host: '',
      port: 5432,
      mode: 'read_only',
      password: 'p',
    });
    expect(errors.host).toContain('required');
  });
});
