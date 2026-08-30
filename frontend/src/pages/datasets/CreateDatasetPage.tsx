import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ArrowLeft, Loader, Database, Table, Eye, AlertCircle, Upload } from 'lucide-react';
import { createDataset, bulkImportFields } from '../../services/datasetService';
import { browseDataSource } from '../../services/datasource';
import { listConnections } from '../../services/connectionService';
import { useWorkspace } from '../../contexts/WorkspaceContext';
import FileUploadModal from '../../components/datasets/FileUploadModal';
import type { BrowseSchema, BrowseSchemaObject } from '../../services/datasource';
import type { DatasetType, Criticality } from '../../types/dataset';
import { useTenantScopedPath } from '../../hooks/useTenantScopedPath';

const CRITICALITIES: Criticality[] = ['low', 'medium', 'high', 'critical'];

export default function CreateDatasetPage() {
  const { workspace_id } = useParams<{ workspace_id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentTenantId } = useWorkspace();
  const { wsPath } = useTenantScopedPath();
  const [uploadOpen, setUploadOpen] = useState(false);

  // ── Form state ──────────────────────────────────────────────────────────
  const [datasetName, setDatasetName] = useState('');
  const [dataSourceId, setDataSourceId] = useState('');
  const [selectedSchema, setSelectedSchema] = useState('');
  const [selectedObject, setSelectedObject] = useState('');
  const [description, setDescription] = useState('');
  const [businessDomain, setBusinessDomain] = useState('');
  const [criticality, setCriticality] = useState<Criticality>('low');
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Derived from selection
  const [physicalIdentifier, setPhysicalIdentifier] = useState('');
  const [schemaName, setSchemaName] = useState('');
  const [datasetType, setDatasetType] = useState<DatasetType>('table');

  // ── Load active data sources authorized to this workspace ─────────────
  // Tenant connections drive workspace authorization (control.workspace_connection_assignments).
  // listConnections({tenant_id, workspace_id}) returns only those assigned to this workspace.
  const { data: dsData } = useQuery({
    queryKey: ['datasets-active-sources', currentTenantId, workspace_id],
    queryFn: () =>
      listConnections(currentTenantId!, {
        workspace_id,
        status: 'active',
        page_size: 100,
      }),
    enabled: !!workspace_id && !!currentTenantId,
    staleTime: 60_000,
  });
  const activeSources = (dsData?.items ?? []).map((c) => ({
    data_source_id: c.connection_id,
    source_name: c.source_name,
    source_type: c.source_type,
  }));

  // ── Browse schema when data source changes ─────────────────────────────
  const {
    data: browseData,
    isLoading: isBrowsing,
    isError: browseError,
    error: browseErrorObj,
  } = useQuery({
    queryKey: ['browse-data-source', workspace_id, dataSourceId],
    queryFn: () => browseDataSource(workspace_id!, dataSourceId),
    enabled: !!workspace_id && !!dataSourceId,
    staleTime: 120_000,
    retry: false,
  });

  const schemas: BrowseSchema[] = browseData?.schemas ?? [];
  const currentSchemaObjects: BrowseSchemaObject[] =
    schemas.find((s) => s.schema_name === selectedSchema)?.objects ?? [];

  // Reset schema/object selection when data source changes
  useEffect(() => {
    setSelectedSchema('');
    setSelectedObject('');
    setPhysicalIdentifier('');
    setSchemaName('');
    setDatasetType('table');
  }, [dataSourceId]);

  // Auto-select schema if only one available
  useEffect(() => {
    if (schemas.length === 1) {
      setSelectedSchema(schemas[0].schema_name);
    }
  }, [schemas]);

  // Reset object selection when schema changes
  useEffect(() => {
    setSelectedObject('');
    setPhysicalIdentifier('');
    setDatasetType('table');
  }, [selectedSchema]);

  // Fill derived fields when an object is selected
  useEffect(() => {
    if (!selectedObject || !selectedSchema) return;
    const obj = currentSchemaObjects.find((o) => o.object_name === selectedObject);
    if (obj) {
      setSchemaName(obj.schema_name);
      setPhysicalIdentifier(obj.object_name);
      setDatasetType(obj.object_type === 'view' ? 'view' : 'table');
    }
  }, [selectedObject, selectedSchema, currentSchemaObjects]);

  // ── Mutation ────────────────────────────────────────────────────────────
  const mutation = useMutation({
    mutationFn: async () => {
      const data = await createDataset(workspace_id!, {
        data_source_id: dataSourceId,
        dataset_name: datasetName,
        dataset_type: datasetType,
        physical_identifier: physicalIdentifier,
        schema_name: schemaName || null,
        description: description || null,
        business_domain: businessDomain || null,
        criticality,
        freshness_expectation: null,
      });

      // Auto-import columns as dataset fields
      const selectedObj = currentSchemaObjects.find(
        (o) => o.object_name === selectedObject,
      );
      if (selectedObj?.columns?.length) {
        await bulkImportFields(workspace_id!, data.dataset_id, {
          mode: 'replace',
          fields: selectedObj.columns.map((col) => ({
            field_name: col.column_name,
            data_type: col.data_type,
            nullable: col.nullable,
            is_key_candidate: col.is_primary_key,
          })),
        });
      }

      return data;
    },
    onSuccess: (data) => {
      toast.success('Dataset registered');
      navigate(wsPath(workspace_id!, `/datasets/${data.dataset_id}`));
    },
    onError: (err: any) => {
      const apiError = err?.response?.data?.error;
      if (apiError?.fields) {
        const fe: Record<string, string> = {};
        for (const f of apiError.fields) fe[f.field] = f.message;
        setErrors(fe);
      } else {
        toast.error(apiError?.message ?? 'Failed to register dataset');
      }
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    const next: Record<string, string> = {};
    if (!datasetName.trim()) next.dataset_name = 'Dataset name is required';
    if (!dataSourceId) next.data_source_id = 'Data source is required';
    if (!selectedObject) next.object = 'Select a table or view';
    if (Object.keys(next).length) {
      setErrors(next);
      return;
    }
    mutation.mutate();
  }

  const inputClass =
    'w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500';
  const labelClass = 'block text-sm font-medium text-gray-300 mb-1';

  const browseErrorMessage =
    browseError && browseErrorObj
      ? (browseErrorObj as any)?.response?.data?.error?.message ?? 'Failed to browse data source'
      : '';

  return (
    <div className="max-w-2xl space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to={`/workspaces/${workspace_id}/datasets`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Datasets
        </Link>
        <h1 className="text-xl font-semibold text-white">Register Dataset</h1>
      </div>

      {/* Source-type selector: existing connection vs file upload */}
      <div className="flex flex-wrap gap-2 text-sm">
        <div className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-purple-600/20 border border-purple-500/40 text-purple-200">
          <Database className="w-4 h-4" />
          From data source
        </div>
        <button
          type="button"
          onClick={() => setUploadOpen(true)}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-gray-300 hover:text-white hover:bg-gray-700 transition-colors"
        >
          <Upload className="w-4 h-4" />
          From file upload
        </button>
      </div>

      {uploadOpen && workspace_id && (
        <FileUploadModal
          workspaceId={workspace_id}
          onClose={() => setUploadOpen(false)}
          onCreated={(datasetId) => {
            setUploadOpen(false);
            queryClient.invalidateQueries({ queryKey: ['datasets', workspace_id] });
            navigate(wsPath(workspace_id!, `/datasets/${datasetId}`));
          }}
        />
      )}

      <form
        onSubmit={handleSubmit}
        noValidate
        data-testid="create-dataset-form"
        className="space-y-5 bg-gray-800/60 border border-gray-700 rounded-2xl p-6"
      >
        {/* ── Step 1: Data Source ────────────────────────────────────────── */}
        <div>
          <label htmlFor="data-source" className={labelClass}>
            <Database className="inline w-4 h-4 mr-1 -mt-0.5" />
            Data Source<span className="text-red-400 ml-0.5">*</span>
          </label>
          <select
            id="data-source"
            data-testid="data-source-select"
            value={dataSourceId}
            onChange={(e) => setDataSourceId(e.target.value)}
            className={inputClass}
          >
            <option value="">— Select active data source —</option>
            {activeSources.map((s: any) => (
              <option key={s.data_source_id} value={s.data_source_id}>
                {s.source_name} ({s.source_type})
              </option>
            ))}
          </select>
          {errors.data_source_id && (
            <p className="mt-1 text-xs text-red-400">{errors.data_source_id}</p>
          )}
        </div>

        {/* ── Step 2: Schema & Object picker ────────────────────────────── */}
        {dataSourceId && (
          <div className="space-y-4 rounded-xl border border-gray-700 bg-gray-900/40 p-4">
            <h3 className="text-sm font-medium text-gray-300">
              Select Table or View
            </h3>

            {isBrowsing && (
              <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
                <Loader className="w-4 h-4 animate-spin" />
                Loading schemas…
              </div>
            )}

            {browseError && (
              <div className="flex items-start gap-2 text-sm text-red-400 py-2">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{browseErrorMessage}</span>
              </div>
            )}

            {!isBrowsing && !browseError && schemas.length === 0 && (
              <p className="text-sm text-gray-500 py-2">
                No schemas found in this data source.
              </p>
            )}

            {!isBrowsing && !browseError && schemas.length > 0 && (
              <>
                {/* Schema dropdown */}
                <div>
                  <label htmlFor="schema-select" className={labelClass}>
                    Schema
                  </label>
                  <select
                    id="schema-select"
                    data-testid="schema-select"
                    value={selectedSchema}
                    onChange={(e) => setSelectedSchema(e.target.value)}
                    className={inputClass}
                  >
                    <option value="">— Select schema —</option>
                    {schemas.map((s) => (
                      <option key={s.schema_name} value={s.schema_name}>
                        {s.schema_name} ({s.objects.length} object{s.objects.length !== 1 ? 's' : ''})
                      </option>
                    ))}
                  </select>
                </div>

                {/* Object dropdown */}
                {selectedSchema && (
                  <div>
                    <label htmlFor="object-select" className={labelClass}>
                      Table / View
                    </label>
                    {currentSchemaObjects.length === 0 ? (
                      <p className="text-sm text-gray-500">No tables or views in this schema.</p>
                    ) : (
                      <select
                        id="object-select"
                        data-testid="object-select"
                        value={selectedObject}
                        onChange={(e) => setSelectedObject(e.target.value)}
                        className={inputClass}
                      >
                        <option value="">— Select table or view —</option>
                        {currentSchemaObjects.map((o) => (
                          <option key={o.object_name} value={o.object_name}>
                            {o.object_type === 'view' ? '📊 ' : '📋 '}
                            {o.object_name} ({o.object_type})
                          </option>
                        ))}
                      </select>
                    )}
                    {errors.object && (
                      <p className="mt-1 text-xs text-red-400">{errors.object}</p>
                    )}
                  </div>
                )}

                {/* Auto-filled fields preview */}
                {selectedObject && (
                  <div className="flex flex-wrap gap-3 pt-1">
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-700 px-3 py-1 text-xs text-gray-200">
                      {datasetType === 'view' ? (
                        <Eye className="w-3 h-3" />
                      ) : (
                        <Table className="w-3 h-3" />
                      )}
                      {datasetType}
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full bg-gray-700 px-3 py-1 text-xs text-gray-200 font-mono">
                      {schemaName}.{physicalIdentifier}
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Step 3: Business metadata ─────────────────────────────────── */}
        <div className="space-y-4 rounded-xl border border-gray-700 bg-gray-900/40 p-4">
          <h3 className="text-sm font-medium text-gray-300">Business Metadata</h3>

          {/* Dataset Name */}
          <div>
            <label htmlFor="dataset-name" className={labelClass}>
              Dataset Name<span className="text-red-400 ml-0.5">*</span>
            </label>
            <input
              id="dataset-name"
              data-testid="dataset-name-input"
              type="text"
              value={datasetName}
              onChange={(e) => setDatasetName(e.target.value)}
              className={inputClass}
              placeholder="e.g. Customer Orders"
            />
            {errors.dataset_name && (
              <p data-testid="dataset-name-error" className="mt-1 text-xs text-red-400">
                {errors.dataset_name}
              </p>
            )}
          </div>

          {/* Description */}
          <div>
            <label htmlFor="description" className={labelClass}>Description</label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={`${inputClass} resize-none`}
              rows={3}
              placeholder="Optional description"
            />
          </div>

          {/* Business Domain */}
          <div>
            <label htmlFor="business-domain" className={labelClass}>Business Domain</label>
            <input
              id="business-domain"
              type="text"
              value={businessDomain}
              onChange={(e) => setBusinessDomain(e.target.value)}
              className={inputClass}
              placeholder="e.g. Finance, Sales"
            />
          </div>

          {/* Criticality */}
          <div>
            <label htmlFor="criticality" className={labelClass}>Criticality</label>
            <select
              id="criticality"
              value={criticality}
              onChange={(e) => setCriticality(e.target.value as Criticality)}
              className={inputClass}
            >
              {CRITICALITIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Submit ────────────────────────────────────────────────────── */}
        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            data-testid="submit-btn"
            disabled={mutation.isPending || !selectedObject}
            className="flex-1 py-2 rounded-lg bg-gradient-to-r from-purple-600 to-blue-600 text-white text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {mutation.isPending ? 'Registering…' : 'Register Dataset'}
          </button>
          <Link
            to={`/workspaces/${workspace_id}/datasets`}
            className="flex-1 py-2 rounded-lg border border-gray-600 text-gray-300 text-sm text-center hover:bg-gray-700 transition-colors"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
