/**
 * F121 — Dataset Profiling Panel
 * Shows column-level statistics for a dataset.
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { BarChart3, ChevronDown, ChevronUp } from 'lucide-react';
import { profileDataset, type DatasetProfile, type ColumnProfile } from '../../services/datasetService';

interface Props {
  workspaceId: string;
  datasetId: string;
  /**
   * F4 — When true, automatically runs the profile once on mount (no toast on
   * success suppression; we keep the same UX), useful when opening a dataset
   * that has never been profiled. Caller is expected to gate this on
   * `dataset.last_profiled_at == null` and write permissions.
   */
  autoRunOnMount?: boolean;
}

function NullBar({ pct }: { pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 h-2 rounded-full bg-gray-700 overflow-hidden">
        <div
          className={`h-full rounded-full ${pct > 50 ? 'bg-red-500' : pct > 10 ? 'bg-yellow-500' : 'bg-green-500'}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-400">{pct.toFixed(1)}%</span>
    </div>
  );
}

function ColumnRow({ col }: { col: ColumnProfile }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr
        className="border-b border-gray-700/50 cursor-pointer hover:bg-gray-700/20"
        onClick={() => setOpen(!open)}
      >
        <td className="px-4 py-2 text-white font-mono text-sm">{col.name}</td>
        <td className="px-4 py-2 text-gray-400 text-xs">{col.data_type}</td>
        <td className="px-4 py-2"><NullBar pct={col.null_percentage} /></td>
        <td className="px-4 py-2 text-gray-300 text-sm">{col.unique_count.toLocaleString()}</td>
        <td className="px-4 py-2 text-gray-300 text-sm">{col.min_value ?? '—'}</td>
        <td className="px-4 py-2 text-gray-300 text-sm">{col.max_value ?? '—'}</td>
        <td className="px-4 py-2">
          {open ? <ChevronUp className="w-3.5 h-3.5 text-gray-500" /> : <ChevronDown className="w-3.5 h-3.5 text-gray-500" />}
        </td>
      </tr>
      {open && (
        <tr className="border-b border-gray-700/50 bg-gray-800/40">
          <td colSpan={7} className="px-6 py-3 text-sm">
            <div className="grid grid-cols-4 gap-4 mb-3">
              {col.mean !== null && <div><span className="text-gray-400">Mean:</span> <span className="text-white">{col.mean.toFixed(2)}</span></div>}
              {col.median !== null && <div><span className="text-gray-400">Median:</span> <span className="text-white">{col.median.toFixed(2)}</span></div>}
              {col.std_dev !== null && <div><span className="text-gray-400">Std Dev:</span> <span className="text-white">{col.std_dev.toFixed(2)}</span></div>}
              <div><span className="text-gray-400">Cardinality:</span> <span className="text-white">{(col.cardinality * 100).toFixed(1)}%</span></div>
            </div>
            {col.top_values.length > 0 && (
              <div>
                <p className="text-gray-400 text-xs mb-1">Top Values</p>
                <div className="flex flex-wrap gap-2">
                  {col.top_values.map((tv, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-700 text-xs text-gray-200">
                      {tv.value} <span className="text-gray-500">({tv.count})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {col.suggested_checks.length > 0 && (
              <div className="mt-2">
                <p className="text-gray-400 text-xs mb-1">Suggested Checks</p>
                <div className="flex flex-wrap gap-1">
                  {col.suggested_checks.map((c, i) => (
                    <span key={i} className="px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 text-xs">{c}</span>
                  ))}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function DatasetProfilingPanel({ workspaceId, datasetId, autoRunOnMount = false }: Props) {
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => profileDataset(workspaceId, datasetId),
    onSuccess: (data) => {
      setProfile(data);
      toast.success(`Profiled ${data.total_columns} columns across ${data.total_rows.toLocaleString()} rows`);
      // Invalidate the detail query so the persisted enrichment renders in the Fields table.
      queryClient.invalidateQueries({ queryKey: ['datasets', workspaceId, datasetId] });
      queryClient.invalidateQueries({ queryKey: ['dataset', workspaceId, datasetId] });
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message ?? 'Profiling failed');
    },
  });

  // F4 — One-shot auto-profile when the panel mounts on an unprofiled dataset.
  const autoRanRef = useRef(false);
  useEffect(() => {
    if (!autoRunOnMount || autoRanRef.current) return;
    autoRanRef.current = true;
    mutation.mutate();
    // mutation reference is stable enough for our one-shot guard; deps kept
    // narrow on purpose to avoid re-firing.
     
  }, [autoRunOnMount, workspaceId, datasetId]);

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/60 overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-700 flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-300 flex items-center gap-2">
          <BarChart3 className="w-4 h-4" /> Data Profile
          {profile && <span className="text-gray-500">({profile.total_columns} columns)</span>}
        </h2>
        <button
          data-testid="run-profile-btn"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="px-3 py-1.5 rounded-lg bg-purple-600 text-white text-sm hover:bg-purple-500 transition-colors disabled:opacity-50"
        >
          {mutation.isPending ? 'Profiling…' : profile ? 'Re-profile' : 'Run Profile'}
        </button>
      </div>

      {!profile && !mutation.isPending && (
        <p className="px-5 py-6 text-center text-gray-400 text-sm">
          Click "Run Profile" to analyze the dataset's columns.
        </p>
      )}

      {mutation.isPending && (
        <div className="px-5 py-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <p className="mt-2 text-gray-400 text-sm">Profiling dataset…</p>
        </div>
      )}

      {profile && profile.columns.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Column</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Type</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Nulls</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Unique</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Min</th>
                <th className="text-left px-4 py-2 text-gray-400 font-medium">Max</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {profile.columns.map((col) => (
                <ColumnRow key={col.name} col={col} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {profile && profile.columns.length === 0 && (
        <p className="px-5 py-6 text-center text-gray-400 text-sm">
          {profile.message ?? 'No columns found.'}
        </p>
      )}
    </div>
  );
}
