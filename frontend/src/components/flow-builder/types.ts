/**
 * Shared types for Flow Builder components
 */

export interface DataSource {
  id: string
  name: string
  type: string
  path?: string
  displayPath?: string
  metadata?: {
    rowCount?: number
    size?: string
    lastModified?: Date
    columns?: any[]
  }
  schema_name?: string
  table_name?: string
  // Dataset-based config properties
  dataset_id?: string
  dataset_name?: string
  physical_identifier?: string
  data_source_name?: string
  field_count?: number
  columns?: any[]
}

export interface DQCheck {
  id: string
  type: string
  category: 'structural' | 'semantic' | 'statistical' | 'governance' | 'reconciliation'
  name: string
  icon: any
  description: string
  color: string
}

export interface FlowNode {
  id: string
  type: 'source' | 'check'
  name?: string
  checkType?: string
  x: number
  y: number
  config?: any
  connections: string[]
  sourceNodeId?: string
}

export interface PromptMessage {
  type: 'info' | 'success' | 'error' | 'question' | 'suggestions'
  text: string
  suggestions?: any[]
}
