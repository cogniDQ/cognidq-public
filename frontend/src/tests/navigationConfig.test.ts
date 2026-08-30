/**
 * F130 P05 — navigationConfig tests
 *
 * Coverage:
 *   1. connections item is in the tenant-admin section
 *   2. glossary item is in the workspace section
 *   3. datasources item is NOT in the workspace section
 *   4. tenant section contains only the workspaces item
 *   5. workspace section still has expected items (regression)
 */
import { NAV_SECTIONS } from '@/config/navigationConfig'

describe('navigationConfig', () => {
  const tenantSection = NAV_SECTIONS.find((s) => s.id === 'tenant')!
  const tenantAdminSection = NAV_SECTIONS.find((s) => s.id === 'tenant-admin')!
  const workspaceSection = NAV_SECTIONS.find((s) => s.id === 'workspace')!

  it('tenant-admin section contains connections item', () => {
    expect(tenantAdminSection.items.some((i) => i.id === 'tenant-connections')).toBe(true)
  })

  it('workspace section contains glossary item', () => {
    expect(workspaceSection.items.some((i) => i.id === 'glossary')).toBe(true)
  })

  it('workspace section does NOT contain datasources item', () => {
    expect(workspaceSection.items.some((i) => i.id === 'datasources')).toBe(false)
  })

  it('tenant section contains only the workspaces item', () => {
    expect(tenantSection.items.map((i) => i.id)).toEqual(['workspaces'])
  })

  it('workspace section still contains expected items (overview, flows, rules)', () => {
    const ids = workspaceSection.items.map((i) => i.id)
    expect(ids).toContain('overview')
    expect(ids).toContain('flows')
    expect(ids).toContain('rules')
  })
})
