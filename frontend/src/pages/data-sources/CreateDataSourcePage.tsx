import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import { createDataSource } from '../../services/datasource';
import type { SourceType, ConnectionMode, DataSourceEnvironment } from '../../types/dataSource';
import SourceTypeCredentialForm from '../../components/data-sources/SourceTypeCredentialForm';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';

const SOURCE_TYPES: SourceType[] = ['postgresql', 'mysql', 'mssql', 'oracle', 'snowflake', 'bigquery'];
const ENVIRONMENTS: DataSourceEnvironment[] = ['development', 'staging', 'production'];
const CONNECTION_MODES: ConnectionMode[] = ['direct', 'agent'];

export default function CreateDataSourcePage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const navigate = useNavigate();
  const { wsPath } = useTenantScopedPath();

  const [sourceName, setSourceName] = useState('');
  const [sourceType, setSourceType] = useState<SourceType>('postgresql');
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>('direct');
  const [environment, setEnvironment] = useState<DataSourceEnvironment>('staging');
  const [description, setDescription] = useState('');
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const mutation = useMutation({
    mutationFn: () => {
      // Build typed credentials object
      let creds: Record<string, unknown> = { ...credentials };
      if (sourceType === 'postgresql' || sourceType === 'mysql' || sourceType === 'mssql' || sourceType === 'oracle') {
        creds = { ...credentials, port: parseInt(credentials.port ?? '5432', 10) };
      }
      return createDataSource(workspace_id!, {
        source_name: sourceName,
        source_type: sourceType,
        connection_mode: connectionMode,
        environment,
        description: description || null,
        credentials: creds as any,
      });
    },
    onSuccess: (data) => {
      toast.success('Data source created');
      navigate(wsPath(workspace_id!, `/data-sources/${data.data_source_id}`));
    },
    onError: (err: any) => {
      const apiError = err?.response?.data?.error;
      if (apiError?.fields) {
        const fieldErrors: Record<string, string> = {};
        for (const fe of apiError.fields) {
          fieldErrors[fe.field] = fe.message;
        }
        setErrors(fieldErrors);
      } else {
        toast.error(apiError?.message ?? 'Failed to create data source');
      }
    },
  });

  function handleCredentialChange(field: string, value: string) {
    setCredentials((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    if (!sourceName.trim()) {
      setErrors({ source_name: 'Source name is required' });
      return;
    }
    mutation.mutate();
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}/data-sources`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Data Sources
        </Link>
        <h1 className="text-xl font-semibold text-white">New Data Source</h1>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-5 bg-gray-800/60 border border-gray-700 rounded-2xl p-6">
        {/* Source Name */}
        <div>
          <label htmlFor="source-name" className="block text-sm font-medium text-gray-300 mb-1">
            Source Name<span className="text-red-400 ml-0.5">*</span>
          </label>
          <input
            id="source-name"
            data-testid="source-name-input"
            type="text"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            placeholder="e.g. production-postgres"
          />
          {errors.source_name && (
            <p className="mt-1 text-xs text-red-400">{errors.source_name}</p>
          )}
        </div>

        {/* Source Type */}
        <div>
          <label htmlFor="source-type" className="block text-sm font-medium text-gray-300 mb-1">
            Source Type<span className="text-red-400 ml-0.5">*</span>
          </label>
          <select
            id="source-type"
            data-testid="source-type-select"
            value={sourceType}
            onChange={(e) => {
              setSourceType(e.target.value as SourceType);
              setCredentials({});
            }}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {SOURCE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        {/* Connection Mode */}
        <div>
          <label htmlFor="connection-mode" className="block text-sm font-medium text-gray-300 mb-1">
            Connection Mode
          </label>
          <select
            id="connection-mode"
            data-testid="connection-mode-select"
            value={connectionMode}
            onChange={(e) => setConnectionMode(e.target.value as ConnectionMode)}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {CONNECTION_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {/* Environment */}
        <div>
          <label htmlFor="environment" className="block text-sm font-medium text-gray-300 mb-1">
            Environment
          </label>
          <select
            id="environment"
            data-testid="environment-select"
            value={environment}
            onChange={(e) => setEnvironment(e.target.value as DataSourceEnvironment)}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            {ENVIRONMENTS.map((env) => <option key={env} value={env}>{env}</option>)}
          </select>
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-1">
            Description
          </label>
          <input
            id="description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            placeholder="Optional description"
          />
        </div>

        {/* Dynamic credential fields */}
        <div>
          <h3 className="text-sm font-medium text-gray-300 mb-3">Connection Credentials</h3>
          <SourceTypeCredentialForm
            sourceType={sourceType}
            credentials={credentials}
            onChange={handleCredentialChange}
          />
        </div>

        {/* API-level error */}
        {errors._general && (
          <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
            {errors._general}
          </div>
        )}

        <div className="flex gap-3 justify-end pt-2">
          <Link
            to={`/workspaces/${workspace_id}/data-sources`}
            className="px-4 py-2 rounded-lg border border-gray-600 text-gray-300 hover:text-white text-sm transition-colors"
          >
            Cancel
          </Link>
          <button
            type="submit"
            data-testid="save-data-source-btn"
            disabled={mutation.isPending}
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
          >
            {mutation.isPending ? 'Creating…' : 'Create Data Source'}
          </button>
        </div>
      </form>
    </div>
  );
}
