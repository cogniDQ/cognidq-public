/**
 * FlowExecutions - View all flow execution history
 */
import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Play,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Loader2,
  Search,
  Filter,
  Calendar,
  BarChart3,
  Eye,
} from 'lucide-react'
import { useWorkspace } from '../contexts/WorkspaceContext'
import { useTenantScopedPath } from '../hooks/useTenantScopedPath'
import flowService, { FlowExecution, ExecutionStatus } from '../services/flow'

export default function FlowExecutions() {
  const { workspace_id: urlWorkspaceId } = useParams()
  const { currentWorkspace } = useWorkspace()
  const activeWorkspaceId = urlWorkspaceId || currentWorkspace?.workspace_id
  const navigate = useNavigate()
  const { wsPath } = useTenantScopedPath()

  const [executions, setExecutions] = useState<FlowExecution[]>([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => {
    if (activeWorkspaceId) {
      loadExecutions()
    }
  }, [currentWorkspace])

  const loadExecutions = async () => {
    if (!activeWorkspaceId) return

    setLoading(true)
    try {
      const data = await flowService.listAllExecutions(activeWorkspaceId)
      setExecutions(data)
    } catch (error) {
      console.error('Error loading executions:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStatusBadge = (status: ExecutionStatus) => {
    const styles = {
      completed: 'bg-green-500/20 text-green-400',
      running: 'bg-blue-500/20 text-blue-400',
      pending: 'bg-yellow-500/20 text-yellow-400',
      failed: 'bg-red-500/20 text-red-400',
      cancelled: 'bg-gray-500/20 text-gray-400',
    }
    return (
      <span className={`px-3 py-1 rounded text-sm font-medium ${styles[status]}`}>
        {status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown'}
      </span>
    )
  }

  const getStatusIcon = (status: ExecutionStatus) => {
    switch (status) {
      case ExecutionStatus.COMPLETED:
        return <CheckCircle className="w-5 h-5 text-green-400" />
      case ExecutionStatus.RUNNING:
        return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
      case ExecutionStatus.PENDING:
        return <Clock className="w-5 h-5 text-yellow-400" />
      case ExecutionStatus.FAILED:
        return <XCircle className="w-5 h-5 text-red-400" />
      case ExecutionStatus.CANCELLED:
        return <AlertCircle className="w-5 h-5 text-gray-400" />
      default:
        return <Play className="w-5 h-5 text-gray-400" />
    }
  }

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-'
    const date = new Date(dateString)
    return date.toLocaleString()
  }

  const formatDuration = (seconds?: number) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    const minutes = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${minutes}m ${secs}s`
  }

  const filteredExecutions = executions.filter(exec => {
    const matchesSearch = searchTerm === '' || 
      exec.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      exec.flow_id.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesStatus = statusFilter === 'all' || exec.status === statusFilter
    return matchesSearch && matchesStatus
  })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold gradient-text mb-2">Flow Execution History</h1>
            <p className="text-gray-400">View and analyze all flow execution jobs</p>
          </div>
          <div className="flex items-center space-x-3">
            <button className="btn-secondary">
              <BarChart3 className="w-4 h-4 mr-2" />
              Analytics
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              placeholder="Search by execution ID or flow ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input w-full pl-10"
            />
          </div>
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="input"
            >
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="running">Running</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Total Executions</span>
            <Play className="w-5 h-5 text-primary-400" />
          </div>
          <div className="text-2xl font-bold text-gray-200">{executions.length}</div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Completed</span>
            <CheckCircle className="w-5 h-5 text-green-400" />
          </div>
          <div className="text-2xl font-bold text-green-400">
            {executions.filter(e => e.status === ExecutionStatus.COMPLETED).length}
          </div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Failed</span>
            <XCircle className="w-5 h-5 text-red-400" />
          </div>
          <div className="text-2xl font-bold text-red-400">
            {executions.filter(e => e.status === ExecutionStatus.FAILED).length}
          </div>
        </div>

        <div className="glass p-5 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm">Running</span>
            <Loader2 className="w-5 h-5 text-blue-400" />
          </div>
          <div className="text-2xl font-bold text-blue-400">
            {executions.filter(e => e.status === ExecutionStatus.RUNNING).length}
          </div>
        </div>
      </div>

      {/* Executions Table */}
      {filteredExecutions.length === 0 ? (
        <div className="glass p-12 text-center rounded-lg">
          <Play className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-gray-300 mb-2">No Executions Found</h3>
          <p className="text-gray-500 mb-6">
            {searchTerm || statusFilter !== 'all'
              ? 'Try adjusting your filters'
              : 'Execute a flow to see results here'}
          </p>
          {!searchTerm && statusFilter === 'all' && (
            <button onClick={() => navigate(activeWorkspaceId ? wsPath(activeWorkspaceId, '/flows') : '/hub/flows')} className="btn-primary">
              Go to Flows
            </button>
          )}
        </div>
      ) : (
        <div className="glass rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-dark-900/50 border-b border-dark-700">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Status</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Execution ID</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Flow</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Started</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Duration</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Nodes</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-400 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-dark-700">
              {filteredExecutions.map(execution => (
                <tr key={execution.id} className="hover:bg-dark-800/30">
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(execution.status)}
                      {getStatusBadge(execution.status)}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-300 font-mono">{execution.id.substring(0, 8)}...</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-300">{execution.flow_id.substring(0, 8)}...</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2 text-sm text-gray-400">
                      <Calendar className="w-4 h-4" />
                      <span>{formatDate(execution.started_at)}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-400">{formatDuration(execution.execution_time_seconds)}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-400">
                      {execution.nodes_passed}/{execution.nodes_executed} passed
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      onClick={() => navigate(`/hub/executions/${execution.id}`)}
                      className="btn-secondary btn-sm"
                    >
                      <Eye className="w-4 h-4 mr-2" />
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
