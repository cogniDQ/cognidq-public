import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { archiveDataSource } from '../../services/datasource';

interface Props {
  workspaceId: string;
  dataSourceId: string;
  dataSourceName: string;
  onClose: () => void;
  onSuccess?: () => void;
}

export default function ArchiveModal({
  workspaceId,
  dataSourceId,
  dataSourceName,
  onClose,
  onSuccess,
}: Props) {
  const qc = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => archiveDataSource(workspaceId, dataSourceId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['data-sources', workspaceId] });
      qc.invalidateQueries({ queryKey: ['data-source', workspaceId, dataSourceId] });
      toast.success('Data source archived');
      onSuccess?.();
      onClose();
    },
    onError: () => {
      toast.error('Failed to archive data source');
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 border border-gray-700 rounded-2xl p-6 w-full max-w-md">
        <h2 className="text-lg font-semibold text-white mb-2">Archive data source?</h2>
        <p className="text-sm text-gray-400 mb-6">
          <strong className="text-white">{dataSourceName}</strong> will be archived and can be
          restored later.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-gray-600 text-gray-300 hover:text-white text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="archive-confirm-btn"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            className="px-4 py-2 rounded-lg bg-red-600/80 hover:bg-red-500 text-white text-sm font-medium transition-colors disabled:opacity-60"
          >
            {mutation.isPending ? 'Archiving…' : 'Archive'}
          </button>
        </div>
      </div>
    </div>
  );
}
