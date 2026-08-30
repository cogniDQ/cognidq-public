/**
 * FileUploadModal — Upload a CSV / Excel / JSON / Parquet file and register
 * it as a "file" dataset. Reuses the ingestion API (upload + profile) and
 * then creates a dataset row + bulk-imports its fields.
 */
import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Upload, X, FileText, Loader2, CheckCircle, AlertCircle, Trash2 } from 'lucide-react';
import { api } from '../../services/api';
import { createDataset, bulkImportFields } from '../../services/datasetService';
import type { Criticality, AddFieldPayload } from '../../types/dataset';

interface ColumnMetadata {
  name: string;
  inferred_type: string;
  nullable: boolean;
  sample_values: any[];
  null_count: number;
  unique_count: number;
}

interface UploadResponse {
  file_id: string;
  file_path: string;
  original_filename: string;
  file_type: string;
  row_count: number;
  file_size: number;
  encoding?: string;
  columns: ColumnMetadata[];
  sample_data: any[];
}

interface ProfileResponse {
  total_rows: number;
  total_columns: number;
  columns: ColumnMetadata[];
  profiled_at: string;
}

const CRITICALITIES: Criticality[] = ['low', 'medium', 'high', 'critical'];

const TYPE_MAP: Record<string, string> = {
  integer: 'INTEGER',
  float: 'FLOAT',
  string: 'VARCHAR',
  boolean: 'BOOLEAN',
  datetime: 'TIMESTAMP',
  date: 'DATE',
};

interface Props {
  workspaceId: string;
  onClose: () => void;
  onCreated: (datasetId: string) => void;
}

export default function FileUploadModal({ workspaceId, onClose, onCreated }: Props) {
  const [uploaded, setUploaded] = useState<UploadResponse | null>(null);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [busy, setBusy] = useState<null | 'uploading' | 'profiling' | 'saving'>(null);
  const [error, setError] = useState<string | null>(null);

  const [datasetName, setDatasetName] = useState('');
  const [description, setDescription] = useState('');
  const [businessDomain, setBusinessDomain] = useState('');
  const [criticality, setCriticality] = useState<Criticality>('low');

  const onDrop = useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    const file = files[0];
    setError(null);
    setBusy('uploading');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await api.post<UploadResponse>('/ingestion/upload', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setUploaded(res.data);
      // Default dataset name from filename without extension
      const base = res.data.original_filename.replace(/\.[^/.]+$/, '');
      setDatasetName(base);

      // Auto-profile right after upload
      setBusy('profiling');
      const profRes = await api.post<ProfileResponse>(
        `/ingestion/workspaces/${workspaceId}/profile`,
        null,
        { params: { file_id: res.data.file_id } },
      );
      setProfile(profRes.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Upload failed');
    } finally {
      setBusy(null);
    }
  }, [workspaceId]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    maxSize: 100 * 1024 * 1024,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.xls'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/json': ['.json', '.jsonl'],
      'application/octet-stream': ['.parquet'],
    },
  });

  const handleDiscard = async () => {
    if (!uploaded) return;
    try {
      await api.delete(`/ingestion/temp-files/${uploaded.file_id}`);
    } catch {
      /* ignore */
    }
    setUploaded(null);
    setProfile(null);
    setError(null);
  };

  const handleSave = async () => {
    if (!uploaded || !workspaceId) return;
    if (datasetName.trim().length < 3) {
      setError('Dataset name must be at least 3 characters.');
      return;
    }
    setError(null);
    setBusy('saving');
    try {
      const ds = await createDataset(workspaceId, {
        dataset_name: datasetName.trim(),
        dataset_type: 'file',
        physical_identifier: uploaded.file_path,
        description: description || null,
        business_domain: businessDomain || null,
        criticality,
      });

      const cols = profile?.columns ?? uploaded.columns;
      const fields: AddFieldPayload[] = cols.map((c) => ({
        field_name: c.name,
        data_type: TYPE_MAP[c.inferred_type] || 'VARCHAR',
        nullable: c.nullable !== false,
      }));
      if (fields.length > 0) {
        await bulkImportFields(workspaceId, ds.dataset_id, {
          mode: 'replace',
          fields,
        });
      }

      onCreated(ds.dataset_id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.response?.data?.message || err.message || 'Failed to save dataset');
    } finally {
      setBusy(null);
    }
  };

  const formatBytes = (b: number) => {
    if (!b) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return `${Math.round((b / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="glass border border-dark-700 rounded-lg w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-dark-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Upload a file</h2>
            <p className="text-sm text-gray-400">CSV, Excel, JSON, or Parquet — registered as a file dataset.</p>
          </div>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-5">
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-300 text-sm">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div>{error}</div>
            </div>
          )}

          {!uploaded && (
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                isDragActive ? 'border-primary-500 bg-primary-500/10' : 'border-dark-700 hover:border-dark-600 bg-dark-900/40'
              } ${busy ? 'pointer-events-none opacity-60' : ''}`}
            >
              <input {...getInputProps()} />
              {busy === 'uploading' || busy === 'profiling' ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="w-10 h-10 text-primary-400 animate-spin" />
                  <p className="text-gray-300 text-sm">{busy === 'uploading' ? 'Uploading…' : 'Profiling…'}</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="w-10 h-10 text-gray-500" />
                  <p className="text-gray-200 font-medium">
                    {isDragActive ? 'Drop the file here' : 'Drag & drop a file here, or click to select'}
                  </p>
                  <p className="text-xs text-gray-500">CSV · XLSX · JSON · JSONL · Parquet — max 100MB</p>
                </div>
              )}
            </div>
          )}

          {uploaded && (
            <>
              <div className="flex items-start justify-between gap-3 p-3 bg-dark-900/40 border border-dark-700 rounded-lg">
                <div className="flex items-start gap-3 min-w-0">
                  <FileText className="w-5 h-5 text-primary-400 mt-0.5 flex-shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-white truncate">{uploaded.original_filename}</div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {uploaded.file_type.toUpperCase()} · {uploaded.row_count.toLocaleString()} rows · {uploaded.columns.length} columns · {formatBytes(uploaded.file_size)}
                    </div>
                  </div>
                </div>
                <button
                  onClick={handleDiscard}
                  disabled={!!busy}
                  className="p-2 text-gray-400 hover:text-red-400 rounded-lg hover:bg-dark-700 flex-shrink-0"
                  title="Discard this file"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-medium text-gray-400 mb-1 block">Dataset name *</label>
                  <input
                    type="text"
                    value={datasetName}
                    onChange={(e) => setDatasetName(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white focus:border-primary-500 focus:outline-none"
                    placeholder="customers_q1"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-400 mb-1 block">Criticality</label>
                  <select
                    value={criticality}
                    onChange={(e) => setCriticality(e.target.value as Criticality)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white focus:border-primary-500 focus:outline-none"
                  >
                    {CRITICALITIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-400 mb-1 block">Business domain</label>
                  <input
                    type="text"
                    value={businessDomain}
                    onChange={(e) => setBusinessDomain(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white focus:border-primary-500 focus:outline-none"
                    placeholder="Sales, Marketing, …"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-400 mb-1 block">Description</label>
                  <input
                    type="text"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    className="w-full bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white focus:border-primary-500 focus:outline-none"
                    placeholder="Optional"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-gray-200">Columns ({uploaded.columns.length})</h3>
                  {profile && (
                    <span className="text-xs text-green-400 flex items-center gap-1">
                      <CheckCircle className="w-3 h-3" /> Profiled
                    </span>
                  )}
                </div>
                <div className="border border-dark-700 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-dark-900/60 text-xs uppercase text-gray-400">
                      <tr>
                        <th className="text-left px-3 py-2">Name</th>
                        <th className="text-left px-3 py-2">Type</th>
                        <th className="text-right px-3 py-2">Nulls</th>
                        <th className="text-right px-3 py-2">Unique</th>
                      </tr>
                    </thead>
                    <tbody>
                      {uploaded.columns.map((c) => (
                        <tr key={c.name} className="border-t border-dark-700/60">
                          <td className="px-3 py-2 text-gray-200 font-mono text-xs">{c.name}</td>
                          <td className="px-3 py-2 text-gray-400 text-xs">{c.inferred_type}</td>
                          <td className="px-3 py-2 text-right text-gray-500 text-xs">{c.null_count}</td>
                          <td className="px-3 py-2 text-right text-gray-500 text-xs">{c.unique_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-dark-700">
          <button
            onClick={onClose}
            disabled={busy === 'saving'}
            className="px-4 py-2 text-sm text-gray-300 hover:text-white rounded-lg hover:bg-dark-700"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!uploaded || !!busy}
            className="px-4 py-2 text-sm font-medium bg-primary-500 hover:bg-primary-600 disabled:bg-dark-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white rounded-lg flex items-center gap-2"
          >
            {busy === 'saving' && <Loader2 className="w-4 h-4 animate-spin" />}
            Save as dataset
          </button>
        </div>
      </div>
    </div>
  );
}
