import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft } from 'lucide-react';
import { getDataset, updateDataset } from '../../services/datasetService';
import type { UpdateDatasetPayload } from '../../types/dataset';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';

export default function EditDatasetPage() {
  const { workspace_id, dataset_id } = useParams<{ workspace_id: string; dataset_id: string }>();
  const navigate = useNavigate();
  const { wsPath } = useTenantScopedPath();

  const { data: dataset, isLoading } = useQuery({
    queryKey: ['dataset', workspace_id, dataset_id],
    queryFn: () => getDataset(workspace_id!, dataset_id!),
    enabled: !!workspace_id && !!dataset_id,
    staleTime: 60_000,
  });

  const [form, setForm] = useState<UpdateDatasetPayload>({
    dataset_name: '',
    description: '',
    business_domain: '',
    criticality: 'medium',
    schema_name: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (dataset) {
      setForm({
        dataset_name: dataset.dataset_name,
        description: dataset.description ?? '',
        business_domain: dataset.business_domain ?? '',
        criticality: dataset.criticality,
        schema_name: dataset.schema_name ?? '',
      });
    }
  }, [dataset]);

  const updateMutation = useMutation({
    mutationFn: (payload: UpdateDatasetPayload) =>
      updateDataset(workspace_id!, dataset_id!, payload),
    onSuccess: () => {
      toast.success('Dataset updated');
      navigate(wsPath(workspace_id!, `/datasets/${dataset_id}`));
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error?.message ?? 'Update failed';
      setErrors({ server: msg });
    },
  });

  function validate() {
    const next: Record<string, string> = {};
    if (!form.dataset_name?.trim()) {
      next.dataset_name = 'Dataset name is required';
    }
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    const payload: UpdateDatasetPayload = {
      dataset_name: form.dataset_name?.trim(),
      description: form.description?.trim() || undefined,
      business_domain: form.business_domain?.trim() || undefined,
      criticality: form.criticality,
      schema_name: form.schema_name?.trim() || undefined,
    };
    updateMutation.mutate(payload);
  }

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse" data-testid="edit-dataset-loading">
        <div className="h-8 w-48 rounded-lg bg-gray-800" />
        <div className="h-64 rounded-2xl bg-gray-800/60" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}/datasets/${dataset_id}`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </Link>
        <h1 className="text-xl font-semibold text-white">Edit Dataset</h1>
      </div>

      {/* Immutable fields (read-only) */}
      {dataset && (
        <div className="rounded-2xl border border-gray-700/50 bg-gray-800/40 p-4 space-y-3 text-sm">
          <p className="text-xs text-gray-500 uppercase tracking-wider font-medium">Read-only fields</p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-gray-400 mb-1">Data Source</p>
              <p className="text-white" data-testid="readonly-data-source">
                {dataset.data_source_name ?? '—'}
              </p>
            </div>
            <div>
              <p className="text-gray-400 mb-1">Dataset Type</p>
              <p className="text-white capitalize" data-testid="readonly-dataset-type">
                {dataset.dataset_type}
              </p>
            </div>
            <div>
              <p className="text-gray-400 mb-1">Physical Identifier</p>
              <p className="text-white font-mono" data-testid="readonly-physical-identifier">
                {dataset.physical_identifier}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Edit form */}
      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-gray-700 bg-gray-800/60 p-5 space-y-4"
        data-testid="edit-dataset-form"
      >
        {errors.server && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-red-400 text-sm">
            {errors.server}
          </div>
        )}

        {/* Dataset Name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Dataset Name *</label>
          <input
            data-testid="dataset-name-input"
            type="text"
            value={form.dataset_name ?? ''}
            onChange={(e) => setForm({ ...form, dataset_name: e.target.value })}
            className="w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
          {errors.dataset_name && (
            <p className="mt-1 text-xs text-red-400" data-testid="dataset-name-error">
              {errors.dataset_name}
            </p>
          )}
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Description</label>
          <textarea
            data-testid="description-input"
            rows={3}
            value={form.description ?? ''}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Business Domain */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Business Domain</label>
          <input
            data-testid="business-domain-input"
            type="text"
            value={form.business_domain ?? ''}
            onChange={(e) => setForm({ ...form, business_domain: e.target.value })}
            className="w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Criticality */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Criticality</label>
          <select
            data-testid="criticality-select"
            value={form.criticality ?? 'medium'}
            onChange={(e) => setForm({ ...form, criticality: e.target.value as any })}
            className="w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>

        {/* Schema Name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1.5">Schema Name</label>
          <input
            data-testid="schema-name-input"
            type="text"
            value={form.schema_name ?? ''}
            onChange={(e) => setForm({ ...form, schema_name: e.target.value })}
            className="w-full rounded-lg border border-gray-600 bg-gray-700/50 px-3 py-2 text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        {/* Submit */}
        <div className="flex justify-end gap-3 pt-2">
          <Link
            to={`/workspaces/${workspace_id}/datasets/${dataset_id}`}
            className="px-4 py-2 rounded-lg border border-gray-600 text-gray-300 text-sm hover:bg-gray-700 transition-colors"
          >
            Cancel
          </Link>
          <button
            data-testid="save-btn"
            type="submit"
            disabled={updateMutation.isPending}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-500 disabled:opacity-50 transition-colors"
          >
            {updateMutation.isPending ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </form>
    </div>
  );
}
