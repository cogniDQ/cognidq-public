import { api } from './api'

export interface GlossaryTerm {
  term_id: string
  workspace_id: string
  business_name: string
  technical_name: string | null
  definition: string | null
  synonyms: string[]
  domain: string | null
  linked_asset_ids: string[]
  source: string
  trust_level: string
  data_type: string | null
  owner: string | null
  is_mandatory: boolean
  allowed_values: string[] | null
  created_at: string | null
}

export interface GlossaryListResponse {
  items: GlossaryTerm[]
  total: number
  page: number
  page_size: number
}

export interface GlossaryTermCreate {
  business_name: string
  technical_name?: string | null
  definition?: string | null
  domain?: string | null
  synonyms?: string[]
  data_type?: string | null
  owner?: string | null
  is_mandatory?: boolean
  allowed_values?: string[] | null
  linked_asset_ids?: string[]
}

export interface GlossaryTermUpdate {
  business_name?: string
  technical_name?: string | null
  definition?: string | null
  domain?: string | null
  synonyms?: string[]
  data_type?: string | null
  owner?: string | null
  is_mandatory?: boolean
  allowed_values?: string[] | null
}

export interface GlossaryImportResult {
  imported: number
  skipped: number
  errors: Array<{ row: number; reason: string }>
}

export async function listGlossaryTerms(
  workspaceId: string,
  params?: { search?: string; domain?: string; page?: number; page_size?: number }
): Promise<GlossaryListResponse> {
  const { data } = await api.get(`/workspaces/${workspaceId}/glossary`, { params })
  return data
}

export async function getGlossaryTerm(
  workspaceId: string,
  termId: string
): Promise<GlossaryTerm> {
  const { data } = await api.get(`/workspaces/${workspaceId}/glossary/${termId}`)
  return data
}

export async function createGlossaryTerm(
  workspaceId: string,
  payload: GlossaryTermCreate
): Promise<GlossaryTerm> {
  const { data } = await api.post(`/workspaces/${workspaceId}/glossary`, payload)
  return data
}

export async function updateGlossaryTerm(
  workspaceId: string,
  termId: string,
  payload: GlossaryTermUpdate
): Promise<GlossaryTerm> {
  const { data } = await api.put(`/workspaces/${workspaceId}/glossary/${termId}`, payload)
  return data
}

export async function deleteGlossaryTerm(
  workspaceId: string,
  termId: string
): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/glossary/${termId}`)
}

export async function importGlossaryCSV(
  workspaceId: string,
  file: File
): Promise<GlossaryImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post(`/workspaces/${workspaceId}/glossary/import-csv`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function exportGlossaryCSV(workspaceId: string): Promise<Blob> {
  const { data } = await api.get(`/workspaces/${workspaceId}/glossary/export-csv`, {
    responseType: 'blob',
  })
  return data
}

// ─────────────────────────────────────────────────────────────────────────────
// F130 — Tenant-scoped glossary API functions
// ─────────────────────────────────────────────────────────────────────────────

export async function listTenantGlossaryTerms(
  tenantId: string,
  params?: { search?: string; domain?: string; page?: number; page_size?: number }
): Promise<GlossaryListResponse> {
  const { data } = await api.get(`/tenants/${tenantId}/glossary`, { params })
  return data
}

export async function createTenantGlossaryTerm(
  tenantId: string,
  payload: GlossaryTermCreate
): Promise<GlossaryTerm> {
  const { data } = await api.post(`/tenants/${tenantId}/glossary`, payload)
  return data
}

export async function updateTenantGlossaryTerm(
  tenantId: string,
  termId: string,
  payload: GlossaryTermUpdate
): Promise<GlossaryTerm> {
  const { data } = await api.put(`/tenants/${tenantId}/glossary/${termId}`, payload)
  return data
}

export async function deleteTenantGlossaryTerm(
  tenantId: string,
  termId: string
): Promise<void> {
  await api.delete(`/tenants/${tenantId}/glossary/${termId}`)
}

export async function importTenantGlossaryCSV(
  tenantId: string,
  file: File
): Promise<GlossaryImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post(`/tenants/${tenantId}/glossary/import`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function exportTenantGlossaryCSV(tenantId: string): Promise<Blob> {
  const { data } = await api.get(`/tenants/${tenantId}/glossary/export`, {
    responseType: 'blob',
  })
  return data
}
