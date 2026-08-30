/**
 * Flow Canvas - Handles the main visual flow canvas with nodes and connections
 */
import { FlowNode, DataSource } from './types'
import { Plus, Settings, GitBranch, Trash2, Copy, Database } from 'lucide-react'
import { deriveNodeStatus, validateConfig, getConfigWarnings, NODE_STATUS_BADGE, NODE_STATUS_TEXT } from '../../schemas/dq-checks/index'

interface FlowCanvasProps {
  nodes: FlowNode[]
  selectedNode: FlowNode | null
  draggedNode: FlowNode | null
  connectionStart: FlowNode | null
  mousePos: { x: number; y: number }
  checks: any[]
  onNodeMouseDown: (e: React.MouseEvent, node: FlowNode) => void
  onNodeClick: (node: FlowNode) => void
  onCanvasMouseMove: (e: React.MouseEvent) => void
  onCanvasMouseUp: () => void
  onStartConnection: (e: React.MouseEvent, node: FlowNode) => void
  onEndConnection: (e: React.MouseEvent, node: FlowNode) => void
  onDeleteNode: (nodeId: string) => void
  onDuplicateNode?: (nodeId: string) => void
}

export function FlowCanvas({
  nodes,
  selectedNode,
  draggedNode,
  connectionStart,
  mousePos,
  checks,
  onNodeMouseDown,
  onNodeClick,
  onCanvasMouseMove,
  onCanvasMouseUp,
  onStartConnection,
  onEndConnection,
  onDeleteNode,
  onDuplicateNode
}: FlowCanvasProps) {
  return (
    <div 
      id="flow-canvas"
      className="flex-1 relative bg-gradient-to-br from-dark-950 to-dark-900 overflow-hidden"
      onMouseMove={onCanvasMouseMove}
      onMouseUp={onCanvasMouseUp}
    >
      {/* Grid Background */}
      <div className="absolute inset-0" style={{
        backgroundImage: 'radial-gradient(circle, rgba(100, 100, 100, 0.1) 1px, transparent 1px)',
        backgroundSize: '20px 20px'
      }} />
      
      {nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <GitBranch className="w-16 h-16 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400 text-lg">Start building your DQ flow</p>
            <p className="text-sm text-gray-600 mt-2">Add a Dataset from the library on the left</p>
          </div>
        </div>
      ) : (
        <div className="relative w-full h-full">
          {/* SVG for Connection Lines */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 1 }}>
            <defs>
              <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="2" orient="auto" markerUnits="strokeWidth">
                <polygon points="0 0, 6 2, 0 4" fill="#1890ff" />
              </marker>
              <marker id="arrowhead-active" markerWidth="6" markerHeight="6" refX="5" refY="2" orient="auto" markerUnits="strokeWidth">
                <polygon points="0 0, 6 2, 0 4" fill="#52c41a" />
              </marker>
            </defs>
            
            {/* Established Connections */}
            {nodes.map(sourceNode => {
              return sourceNode.connections.map(targetId => {
                const targetNode = nodes.find(n => n.id === targetId)
                if (!targetNode) {
                  console.warn(`⚠️ Target node ${targetId} not found for source ${sourceNode.id}`)
                  return null
                }
                
                const x1 = sourceNode.x + 240
                const y1 = sourceNode.y + 60
                const x2 = targetNode.x
                const y2 = targetNode.y + 60
                
                const dx = x2 - x1
                const controlPointOffset = Math.abs(dx) * 0.5
                const path = `M ${x1} ${y1} C ${x1 + controlPointOffset} ${y1}, ${x2 - controlPointOffset} ${y2}, ${x2} ${y2}`
                
                return (
                  <path
                    key={`${sourceNode.id}-${targetId}`}
                    d={path}
                    stroke="#52c41a"
                    strokeWidth="3"
                    fill="none"
                    markerEnd="url(#arrowhead-active)"
                    style={{ filter: 'drop-shadow(0 0 4px rgba(82, 196, 26, 0.3))' }}
                  />
                )
              })
            })}
            
            {/* Active Connection Being Drawn */}
            {connectionStart && (() => {
              const x1 = connectionStart.x + (connectionStart.type === 'source' ? 240 : 96)
              const y1 = connectionStart.y + 60
              const x2 = mousePos.x
              const y2 = mousePos.y
              const dx = x2 - x1
              const controlPointOffset = Math.abs(dx) * 0.5
              const path = `M ${x1} ${y1} C ${x1 + controlPointOffset} ${y1}, ${x2 - controlPointOffset} ${y2}, ${x2} ${y2}`
              
              return (
                <path
                  d={path}
                  stroke="#1890ff"
                  strokeWidth="2"
                  fill="none"
                  strokeDasharray="8,4"
                  markerEnd="url(#arrowhead)"
                  style={{ filter: 'drop-shadow(0 0 4px rgba(24, 144, 255, 0.3))' }}
                />
              )
            })()}
          </svg>

          {/* Flow Nodes - Wrapper with higher z-index */}
          <div className="absolute inset-0" style={{ zIndex: 10 }}>
            {nodes.map(node => {
              if (node.type === 'source') {
                return <SourceNode 
                  key={node.id} 
                  node={node} 
                  isSelected={selectedNode?.id === node.id}
                  isDragged={draggedNode?.id === node.id}
                  onMouseDown={onNodeMouseDown}
                  onClick={onNodeClick}
                  onStartConnection={onStartConnection}
                  onDelete={onDeleteNode}
                />
              } else {
                const check = checks.find(c => c.type === node.checkType)
                if (!check) return null
                
                const sourceNode = nodes.find(n => n.connections.includes(node.id))
                const connectedSource = sourceNode?.config

                return <CheckNode
                  key={node.id}
                  node={node}
                  check={check}
                  connectedSource={connectedSource}
                  isSelected={selectedNode?.id === node.id}
                  isDragged={draggedNode?.id === node.id}
                  onMouseDown={onNodeMouseDown}
                  onClick={onNodeClick}
                  onEndConnection={onEndConnection}
                  onDelete={onDeleteNode}
                  onDuplicate={onDuplicateNode}
                />
              }
            })}
          </div>

          {/* Empty State for Checks */}
          {nodes.filter(n => n.type === 'check').length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="glass p-8 border-2 border-dashed border-dark-700 rounded-lg text-center max-w-md">
                <Plus className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400">Add checks from the library to build your DQ flow</p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Source Node Component
function SourceNode({ node, isSelected, isDragged, onMouseDown, onClick, onStartConnection, onDelete }: any) {
  const sourceData = (node.config && (node.config.dataset_id || node.config.id || node.config.name)) ? node.config as DataSource : null
  
  return (
    <div
      className={`absolute cursor-move ${isSelected ? 'ring-2 ring-primary-500' : ''}`}
      style={{ left: node.x, top: node.y, zIndex: isDragged ? 1000 : 'auto' }}
      onMouseDown={(e) => onMouseDown(e, node)}
      onClick={() => onClick(node)}
    >
      <div className={`glass p-4 rounded-lg border-2 ${
        sourceData ? 'border-primary-500/50' : 'border-yellow-500/50'
      } shadow-glow w-60`}>
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center space-x-3 flex-1 min-w-0">
            <Database className="w-6 h-6 text-primary-400 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-semibold text-white truncate">
                {node.name || sourceData?.dataset_name || sourceData?.name || 'Dataset'}
              </div>
              {sourceData?.physical_identifier && (
                <div className="text-xs text-gray-500 truncate">{sourceData.physical_identifier}</div>
              )}
              {sourceData?.data_source_name && (
                <div className="text-xs text-gray-500 truncate">{sourceData.data_source_name}</div>
              )}
              {!sourceData?.physical_identifier && sourceData?.displayPath && (
                <div className="text-xs text-gray-500 truncate">{sourceData.displayPath}</div>
              )}
            </div>
          </div>
          {isSelected && (
            <button onClick={(e) => { e.stopPropagation(); onDelete(node.id) }} className="text-red-400 hover:text-red-300 ml-2">
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>

        {sourceData?.metadata && (
          <div className="text-xs text-gray-400 space-y-1 mb-2">
            {sourceData.metadata.rowCount && <div>{sourceData.metadata.rowCount.toLocaleString()} rows</div>}
            {sourceData.metadata.columns && Array.isArray(sourceData.metadata.columns) && <div>{sourceData.metadata.columns.length} columns</div>}
            {sourceData.field_count && !sourceData.metadata.columns && <div>{sourceData.field_count} fields</div>}
          </div>
        )}

        {!sourceData && (
          <button onClick={(e) => { e.stopPropagation(); onClick(node) }} className="w-full px-2 py-1.5 bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-400 rounded text-xs mb-2">
            <Settings className="w-3 h-3 inline mr-1" />
            Configure Dataset
          </button>
        )}

        <div className={`absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 ${sourceData ? 'bg-primary-600' : 'bg-yellow-600'} rounded-full border-2 border-dark-950 cursor-crosshair hover:bg-primary-500 flex items-center justify-center`}
          onMouseDown={(e) => onStartConnection(e, node)}
          title="Drag to connect to a check"
        >
          <Plus className="w-3 h-3 text-white" />
        </div>
      </div>
    </div>
  )
}

// Check Node Component
function CheckNode({ node, check, connectedSource, isSelected, isDragged, onMouseDown, onClick, onEndConnection, onDelete, onDuplicate }: any) {
  const Icon = check.icon
  const hasSource = !!connectedSource
  const dimension = node.checkType || ''
  const config = node.config || {}
  const errors = validateConfig(dimension, config, hasSource)
  const nodeStatus = deriveNodeStatus(hasSource, config, errors, dimension)
  const badge = NODE_STATUS_BADGE[nodeStatus]
  const statusLabel = NODE_STATUS_TEXT[nodeStatus]
  const warnings = nodeStatus === 'WARNING' ? getConfigWarnings(config) : []
  const ruleName = config.rule_name || config.ruleName

  return (
    <div
      className={`absolute cursor-move ${isSelected ? 'ring-2 ring-primary-500' : ''}`}
      style={{ left: node.x, top: node.y, zIndex: isDragged ? 1000 : 'auto' }}
      onMouseDown={(e) => onMouseDown(e, node)}
      onClick={() => onClick(node)}
    >
      <div className={`glass p-4 rounded-lg border-2 ${connectedSource ? 'border-green-500/50' : 'border-dark-700'} w-48`}>
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center space-x-2 flex-1">
            <div className={`w-8 h-8 rounded ${check.color} bg-opacity-20 flex items-center justify-center flex-shrink-0`}>
              <Icon className="w-4 h-4 text-white" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-white truncate">{node.name || check.name}</div>
              <div className="text-xs text-gray-500">{check.type}</div>
            </div>
          </div>
          {isSelected && (
            <div className="flex items-center gap-1">
              {onDuplicate && (
                <button onClick={(e) => { e.stopPropagation(); onDuplicate(node.id) }} className="text-gray-400 hover:text-primary-400" title="Duplicate">
                  <Copy className="w-3 h-3" />
                </button>
              )}
              <button onClick={(e) => { e.stopPropagation(); onDelete(node.id) }} className="text-red-400 hover:text-red-300" title="Delete">
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>

        <div className="space-y-1.5 text-xs">
          {/* 6-state status badge */}
          <div className="flex items-center justify-between">
            <span className="text-gray-500">Status:</span>
            <span className={`flex items-center space-x-1 ${badge.color}`}>
              <span>{badge.symbol}</span>
              <span>{statusLabel}</span>
            </span>
          </div>
          {/* Warning details */}
          {warnings.length > 0 && warnings.map((w, i) => (
            <div key={i} className="text-xs text-orange-400/80 truncate" title={w}>
              {w}
            </div>
          ))}
          {/* Rule name if set */}
          {ruleName && (
            <div className="text-xs text-gray-400 truncate" title={ruleName}>
              {ruleName}
            </div>
          )}
          {connectedSource && (
            <div className="text-xs text-gray-500 truncate">Source: {connectedSource.name}</div>
          )}
          <button onClick={(e) => { e.stopPropagation(); onClick(node) }} className="w-full px-2 py-1.5 bg-primary-600/20 hover:bg-primary-600/30 text-primary-400 rounded text-xs">
            <Settings className="w-3 h-3 inline mr-1" />
            Configure
          </button>
        </div>

        <div className="absolute -left-3 top-1/2 -translate-y-1/2 w-6 h-6 bg-dark-700 rounded-full border-2 border-dark-950 cursor-crosshair hover:bg-primary-500"
          onMouseUp={(e) => onEndConnection(e, node)}
          title="Connect data source here"
        />
      </div>
    </div>
  )
}
