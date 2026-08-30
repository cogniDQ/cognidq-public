/**
 * FlowsList - Browse and manage DQ flows
 */
import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Plus,
  Search,
  Filter,
  Play,
  Edit,
  Trash2,
  Copy,
  Download,
  Calendar,
  Clock,
  AlertCircle,
  GitBranch,
  Loader2,
} from 'lucide-react'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useTenantScopedPath } from '../hooks/useTenantScopedPath'
import flowService, { Flow, FlowStatus } from '../services/flow'
import toast from 'react-hot-toast'

export default function FlowsList() {
  const navigate = useNavigate()
  const { workspace_id: urlWorkspaceId } = useParams()
  const { currentWorkspace } = useWorkspace()
  const activeWorkspaceId = urlWorkspaceId || currentWorkspace?.workspace_id
  const { wsPath } = useTenantScopedPath()

  const [flows, setFlows] = useState<Flow[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<FlowStatus | 'all'>('all')
  const [executing, setExecuting] = useState<string | null>(null)
  const [flowToDelete, setFlowToDelete] = useState<Flow | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

  useEffect(() => {
    if (activeWorkspaceId) {
      loadFlows()
    }
  }, [currentWorkspace, statusFilter])

  const loadFlows = async () => {
    if (!activeWorkspaceId) return

    setLoading(true)
    try {
      const params = statusFilter !== 'all' ? { status: statusFilter } : {}
      const data = await flowService.listFlows(activeWorkspaceId, params)
      // Ensure data is always an array and filter out archived flows if not explicitly requested
      const flowsArray = Array.isArray(data) ? data : []
      // Exclude archived flows from the default view unless user specifically filters for them
      const filteredFlows = statusFilter === FlowStatus.ARCHIVED 
        ? flowsArray 
        : flowsArray.filter(f => f.status !== FlowStatus.ARCHIVED)
      setFlows(filteredFlows)
    } catch (error) {
      console.error('Error loading flows:', error)
      toast.error('Failed to load flows')
      setFlows([]) // Set to empty array on error
    } finally {
      setLoading(false)
    }
  }

  const flowBuilderBase = urlWorkspaceId
    ? wsPath(urlWorkspaceId, '/flow-builder')
    : '/hub/flow-builder'

  const handleCreateNew = () => {
    navigate(flowBuilderBase)
  }

  const handleEdit = (flowId: string) => {
    navigate(`${flowBuilderBase}?id=${flowId}`)
  }

  const handleExecute = async (flow: Flow) => {
    if (!activeWorkspaceId) return

    setExecuting(flow.id)
    try {
      await flowService.executeFlow(activeWorkspaceId, flow.id)
      // Navigate to flow builder with runs tab active
      navigate(`${flowBuilderBase}?id=${flow.id}&tab=runs`)
    } catch (error: any) {
      console.error('Error executing flow:', error)
      toast.error(`Failed to execute flow: ${error.response?.data?.detail || error.message}`)
      setExecuting(null)
    }
  }

  const handleDelete = (flow: Flow) => {
    setFlowToDelete(flow)
    setDeleteConfirmText('')
  }

  const confirmDelete = async () => {
    if (!activeWorkspaceId || !flowToDelete) return
    if (deleteConfirmText !== 'confirm') return

    try {
      // Hard delete (permanent deletion)
      await flowService.deleteFlow(activeWorkspaceId, flowToDelete.id, true)
      await loadFlows()
      setFlowToDelete(null)
      setDeleteConfirmText('')
    } catch (error: any) {
      console.error('Error deleting flow:', error)
      toast.error(`Failed to delete flow: ${error.response?.data?.detail || error.message}`)
    }
  }

  const cancelDelete = () => {
    setFlowToDelete(null)
    setDeleteConfirmText('')
  }

  const handleDuplicate = async (flow: Flow) => {
    if (!activeWorkspaceId) return

    try {
      await flowService.duplicateFlow(activeWorkspaceId, flow.id, `${flow.name} (Copy)`)
      await loadFlows()
    } catch (error: any) {
      console.error('Error duplicating flow:', error)
      toast.error(`Failed to duplicate flow: ${error.response?.data?.detail || error.message}`)
    }
  }

  const handleExport = async (flow: Flow) => {
    if (!activeWorkspaceId) return

    try {
      const data = await flowService.exportFlow(activeWorkspaceId, flow.id, 'json')
      const blob = new Blob([data], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${flow.name.replace(/\s+/g, '_')}_flow.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (error: any) {
      console.error('Error exporting flow:', error)
      toast.error(`Failed to export flow: ${error.response?.data?.detail || error.message}`)
    }
  }

  const getStatusBadge = (status: FlowStatus) => {
    const styles = {
      draft: 'bg-gray-500/20 text-gray-400',
      active: 'bg-green-500/20 text-green-400',
      inactive: 'bg-yellow-500/20 text-yellow-400',
      archived: 'bg-red-500/20 text-red-400',
    }
    return (
      <span className={`px-2 py-1 rounded text-xs font-medium ${styles[status]}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    )
  }

  const filteredFlows = Array.isArray(flows) ? flows.filter((flow) =>
    flow.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    flow.description?.toLowerCase().includes(searchTerm.toLowerCase())
  ) : []

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold gradient-text mb-2">DQ Flows</h1>
          <p className="text-gray-400">Manage your data quality flow orchestrations</p>
        </div>
        <button onClick={handleCreateNew} className="btn-primary flex items-center space-x-2">
          <Plus className="w-4 h-4" />
          <span>Create Flow</span>
        </button>
      </div>

      {/* Filters */}
      <div className="glass p-4 rounded-lg mb-6">
        <div className="flex items-center space-x-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search flows..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input pl-10 w-full"
            />
          </div>
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as FlowStatus | 'all')}
              className="input"
            >
              <option value="all">All Statuses</option>
              <option value={FlowStatus.DRAFT}>Draft</option>
              <option value={FlowStatus.ACTIVE}>Active</option>
              <option value={FlowStatus.INACTIVE}>Inactive</option>
              <option value={FlowStatus.ARCHIVED}>Archived</option>
            </select>
          </div>
        </div>
      </div>

      {/* Flows Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
        </div>
      ) : filteredFlows.length === 0 ? (
        <div className="glass p-12 text-center rounded-lg">
          <GitBranch className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-300 mb-2">
            {searchTerm ? 'No flows found' : 'No flows yet'}
          </h3>
          <p className="text-gray-500 mb-6">
            {searchTerm
              ? 'Try adjusting your search or filters'
              : 'Create your first data quality flow to get started'}
          </p>
          {!searchTerm && (
            <button onClick={handleCreateNew} className="btn-primary">
              Create Your First Flow
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredFlows.map((flow) => (
            <div 
              key={flow.id} 
              className="glass p-5 rounded-lg hover:border-primary-500/50 transition-all group cursor-pointer"
              onClick={() => handleEdit(flow.id)}
            >
              {/* Header */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-lg text-gray-200 mb-1 truncate">
                    {flow.name}
                  </h3>
                  {flow.description && (
                    <p className="text-sm text-gray-500 line-clamp-2">{flow.description}</p>
                  )}
                </div>
                {getStatusBadge(flow.status)}
              </div>

              {/* Stats */}
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div className="glass p-2 rounded">
                  <div className="text-xs text-gray-500 mb-1">Nodes</div>
                  <div className="text-lg font-semibold text-primary-400">
                    {flow.flow_definition.nodes.length}
                  </div>
                </div>
                <div className="glass p-2 rounded">
                  <div className="text-xs text-gray-500 mb-1">Executions</div>
                  <div className="text-lg font-semibold text-primary-400">
                    {flow.execution_count}
                  </div>
                </div>
              </div>

              {/* Metadata */}
              <div className="space-y-2 mb-4 text-xs text-gray-500">
                <div className="flex items-center space-x-2">
                  <Calendar className="w-3 h-3" />
                  <span>Created {new Date(flow.created_at).toLocaleDateString()}</span>
                </div>
                {flow.last_executed_at && (
                  <div className="flex items-center space-x-2">
                    <Clock className="w-3 h-3" />
                    <span>Last run {new Date(flow.last_executed_at).toLocaleDateString()}</span>
                  </div>
                )}
                {flow.tags && flow.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {flow.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 bg-primary-500/20 text-primary-400 rounded text-xs"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-2 pt-3 border-t border-dark-700" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => handleExecute(flow)}
                  disabled={executing === flow.id || flow.status !== FlowStatus.ACTIVE}
                  className="flex-1 btn-primary text-xs py-1.5 disabled:opacity-50 flex items-center justify-center"
                  title={flow.status !== FlowStatus.ACTIVE ? 'Flow must be active to execute' : ''}
                  data-testid={`flow-execute-btn-${flow.id}`}
                >
                  {executing === flow.id ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <>
                      <Play className="w-3 h-3 mr-1" />
                      <span>Execute</span>
                    </>
                  )}
                </button>
                <button
                  onClick={() => handleEdit(flow.id)}
                  className="p-1.5 glass hover:bg-dark-700 rounded"
                  title="Edit flow"
                >
                  <Edit className="w-3 h-3" />
                </button>
                <button
                  onClick={() => handleDuplicate(flow)}
                  className="p-1.5 glass hover:bg-dark-700 rounded"
                  title="Duplicate flow"
                >
                  <Copy className="w-3 h-3" />
                </button>
                <button
                  onClick={() => handleExport(flow)}
                  className="p-1.5 glass hover:bg-dark-700 rounded"
                  title="Export flow"
                >
                  <Download className="w-3 h-3" />
                </button>
                <button
                  onClick={() => handleDelete(flow)}
                  className="p-1.5 glass hover:bg-red-500/20 hover:text-red-400 rounded"
                  title="Delete flow"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {flowToDelete && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={cancelDelete}>
          <div 
            className="bg-dark-900 rounded-lg max-w-lg w-full mx-4 border border-dark-700 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-dark-700">
              <h3 className="text-lg font-semibold text-white">Delete flow</h3>
              <button
                onClick={cancelDelete}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Content */}
            <div className="p-4">
              <p className="text-gray-300 mb-3">
                Permanently delete flow <span className="font-semibold text-white">{flowToDelete.name}</span>? You can't undo this action.
              </p>

              {/* Warning Box */}
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-3 mb-4">
                <div className="flex items-start space-x-2">
                  <AlertCircle className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-yellow-200">
                    <p>Proceeding with this action will delete the flow with all its content and can affect related resources.</p>
                  </div>
                </div>
              </div>

              <p className="text-sm text-gray-400 mb-2">
                To avoid accidental deletions, we ask you to provide additional written consent.
              </p>

              <p className="text-sm text-gray-300 mb-2">
                To confirm this deletion, type <span className="font-semibold">"confirm"</span>.
              </p>

              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-600 rounded text-white text-sm focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                placeholder="confirm"
                autoFocus
              />
            </div>

            {/* Footer */}
            <div className="flex justify-end space-x-3 p-4 border-t border-dark-700">
              <button
                onClick={cancelDelete}
                className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteConfirmText !== 'confirm'}
                className="px-4 py-2 text-sm font-medium bg-red-600 hover:bg-red-700 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-red-600"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
