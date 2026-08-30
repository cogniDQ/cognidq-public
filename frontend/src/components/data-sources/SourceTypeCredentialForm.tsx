import type { SourceType } from '../../types/dataSource';

interface FieldProps {
  id: string;
  label: string;
  name: string;
  type?: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  required?: boolean;
  placeholder?: string;
}

function CredentialField({
  id,
  label,
  name,
  type = 'text',
  value,
  onChange,
  required,
  placeholder,
}: FieldProps) {
  const isPassword = type === 'password';
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-300 mb-1">
        {label}
        {required && <span className="text-red-400 ml-0.5">*</span>}
      </label>
      <input
        id={id}
        name={name}
        type={isPassword ? 'password' : type}
        autoComplete={isPassword ? 'new-password' : 'off'}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
      />
    </div>
  );
}

interface Props {
  sourceType: SourceType;
  credentials: Record<string, string>;
  onChange: (field: string, value: string) => void;
}

export default function SourceTypeCredentialForm({ sourceType, credentials, onChange }: Props) {
  const field = (name: string) => credentials[name] ?? '';
  const handle = (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange(e.target.name, e.target.value);

  if (sourceType === 'snowflake') {
    return (
      <div className="space-y-3">
        <CredentialField id="sf-account-identifier" label="Account Identifier" name="account_identifier" value={field('account_identifier')} onChange={handle} required />
        <CredentialField id="sf-account" label="Account" name="account" value={field('account')} onChange={handle} required />
        <CredentialField id="sf-warehouse" label="Warehouse" name="warehouse" value={field('warehouse')} onChange={handle} required />
        <CredentialField id="sf-database" label="Database" name="database" value={field('database')} onChange={handle} required />
        <CredentialField id="sf-username" label="Username" name="username" value={field('username')} onChange={handle} required />
        <CredentialField id="sf-password" label="Password" name="password" type="password" value={field('password')} onChange={handle} required />
      </div>
    );
  }

  if (sourceType === 'bigquery') {
    return (
      <div className="space-y-3">
        <CredentialField id="bq-project-id" label="Project ID" name="project_id" value={field('project_id')} onChange={handle} required />
        <div>
          <label htmlFor="bq-sa-json" className="block text-sm font-medium text-gray-300 mb-1">
            Service Account JSON<span className="text-red-400 ml-0.5">*</span>
          </label>
          <textarea
            id="bq-sa-json"
            name="service_account_json"
            autoComplete="off"
            rows={5}
            value={field('service_account_json')}
            onChange={(e) => onChange('service_account_json', e.target.value)}
            placeholder='{"type": "service_account", ...}'
            required
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>
      </div>
    );
  }

  // postgresql | mysql | mssql | oracle — all use JDBC-style credentials
  return (
    <div className="space-y-3">
      <CredentialField id="jdbc-host" label="Host" name="host" value={field('host')} onChange={handle} required placeholder="db.example.com" />
      <CredentialField id="jdbc-port" label="Port" name="port" type="number" value={field('port')} onChange={handle} required placeholder={sourceType === 'mysql' ? '3306' : sourceType === 'mssql' ? '1433' : sourceType === 'oracle' ? '1521' : '5432'} />
      <CredentialField id="jdbc-database" label="Database" name="database" value={field('database')} onChange={handle} required />
      <CredentialField id="jdbc-username" label="Username" name="username" value={field('username')} onChange={handle} required />
      <CredentialField id="jdbc-password" label="Password" name="password" type="password" value={field('password')} onChange={handle} required />
    </div>
  );
}
