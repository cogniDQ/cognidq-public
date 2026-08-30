import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import { getDataSource, updateDataSource } from '../../services/datasource';
import type { DataSourceEnvironment } from '../../types/dataSource';
import SourceTypeCredentialForm from '../../components/data-sources/SourceTypeCredentialForm';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';

const ENVIRONMENTS: DataSourceEnvironment[] = ['development', 'staging', 'production'];

export default function EditDataSourcePage() {
  const { workspace_id, data_source_id } = useParams<{
    workspace_id: string;
    data_source_id: string;
  }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { wsPath } = useTenantScopedPath();

  const [sourceName, setSourceName] = useState('');
  const [environment, setEnvironment] = useState<DataSourceEnvironment>('staging');
  const [description, setDescription] = useState('');
  const [rotateCredentials, setRotateCredentials] = useState(false);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const queryKey = ['data-source', workspace_id, data_source_id];

  const { data: ds, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getDataSource(workspace_id!, data_source_id!),
    enabled: !!(workspace_id && data_source_id),
    staleTime: 30_000,
  });

  // Pre-populate form when data loads
  useEffect(() => {
    if (ds) {
      setSourceName(ds.source_name);
      setEnvironment(ds.environment);
      setDescription(ds.description ?? '');
    }
  }, [ds]);

  const mutation = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = {
        source_name: sourceName,
        environment,
        description: description || null,
      };
      if (rotateCredentials) {
        let creds: Record<string, unknown> = { ...credentials };
        const t = ds?.source_type;
        if (t === 'postgresql' || t === 'mysql' || t === 'mssql' || t === 'oracle') {
          creds = { ...credentials, port: parseInt(credentials.port ?? '5432', 10) };
        }
        payload.credentials = creds;
      }
      return updateDataSource(workspace_id!, data_source_id!, payload as any);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
      qc.invalidateQueries({ queryKey: ['data-sources', workspace_id] });
      toast.success('Data source updated');
      navigate(wsPath(workspace_id!, `/data-sources/${data_source_id}`));
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
        toast.error(apiError?.message ?? 'Failed to update data source');
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

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-48 rounded-lg bg-gray-800" />
        <div className="h-64 rounded-2xl bg-gray-800/60" />
      </div>
    );
  }

  if (isError || !ds) {
    return (
      <div
        role="alert"
        className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm"
      >
        Failed to load data source.
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}/data-sources/${data_source_id}`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {ds.source_name}
        </Link>
        <h1 className="text-xl font-semibold text-white">Edit Data Source</h1>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-5 bg-gray-800/60 border border-gray-700 rounded-2xl p-6">
        {/* Read-only fields */}
        <div className="grid grid-cols-2 gap-4 p-4 rounded-lg bg-gray-900/50 border border-gray-700/50">
          <div>
            <p className="text-xs text-gray-400">Source Type</p>
            <p className="text-sm text-white font-medium mt-0.5">{ds.source_type}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400">Connection Mode</p>
            <p className="text-sm text-white font-medium mt-0.5">{ds.connection_mode}</p>
          </div>
        </div>

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
          />
          {errors.source_name && (
            <p className="mt-1 text-xs text-red-400">{errors.source_name}</p>
          )}
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
          />
        </div>

        {/* Credential rotation toggle */}
        <div className="border-t border-gray-700 pt-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <div className="relative">
              <input
                type="checkbox"
                data-testid="rotate-credentials-toggle"
                checked={rotateCredentials}
                onChange={(e) => {
                  setRotateCredentials(e.target.checked);
                  if (!e.target.checked) setCredentials({});
                }}
                className="sr-only peer"
              />
              <div className="w-10 h-5 bg-gray-600 rounded-full peer peer-checked:bg-purple-600 transition-colors" />
              <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-5" />
            </div>
            <span className="text-sm font-medium text-gray-300">Rotate Credentials</span>
          </label>
        </div>

        {rotateCredentials && (
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-3">New Credentials</h3>
            <SourceTypeCredentialForm
              sourceType={ds.source_type}
              credentials={credentials}
              onChange={handleCredentialChange}
            />
          </div>
        )}

        <div className="flex gap-3 justify-end pt-2">
          <Link
            to={`/workspaces/${workspace_id}/data-sources/${data_source_id}`}
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
            {mutation.isPending ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  );
}
