// Sprint 4.2 — Evidence panel: synthesized SQL + violations + failing sample rows.
import { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import { Copy, Code2, AlertTriangle, Table } from 'lucide-react'
import type { NodeResultSummary } from '../../types/issue'

interface Props {
  nodeResult: NodeResultSummary
}

function qualifiedTable(nr: NodeResultSummary): string {
  if (nr.dataset) return nr.dataset
  if (nr.schema_name && nr.table_name) return `${nr.schema_name}.${nr.table_name}`
  return nr.table_name || 'target_table'
}

function quoteCol(c: string): string {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(c) ? c : `"${c.replace(/"/g, '""')}"`
}

/**
 * Synthesize a representative SQL query for the check. The runtime engine may
 * use a different dialect or planner, but this gives auditors and analysts a
 * faithful, copy-pasteable representation of the predicate being evaluated.
 */
function synthesizeSql(nr: NodeResultSummary): string {
  const table = qualifiedTable(nr)
  const cols = (nr.columns && nr.columns.length > 0 ? nr.columns : ['*']).map(quoteCol)
  const checkType = (nr.check_type || '').toLowerCase()
  const colList = cols.join(', ')
  const firstCol = cols[0] && cols[0] !== '*' ? cols[0] : null

  switch (checkType) {
    case 'completeness':
    case 'not_null':
      return firstCol
        ? `-- Completeness: rows where ${firstCol} is missing\nSELECT ${colList}\nFROM ${table}\nWHERE ${firstCol} IS NULL\n   OR ${firstCol} = '';`
        : `SELECT ${colList} FROM ${table};`
    case 'uniqueness':
    case 'unique':
      return firstCol
        ? `-- Uniqueness: groups violating the uniqueness constraint\nSELECT ${firstCol}, COUNT(*) AS occurrences\nFROM ${table}\nGROUP BY ${firstCol}\nHAVING COUNT(*) > 1;`
        : `SELECT ${colList} FROM ${table};`
    case 'validity':
    case 'format':
    case 'pattern':
      return firstCol
        ? `-- Validity: rows whose ${firstCol} fails the pattern check\nSELECT ${colList}\nFROM ${table}\nWHERE ${firstCol} !~ '<pattern>';`
        : `SELECT ${colList} FROM ${table};`
    case 'range':
    case 'min_max':
      return firstCol
        ? `-- Range: rows whose ${firstCol} is outside the allowed range\nSELECT ${colList}\nFROM ${table}\nWHERE ${firstCol} < <min> OR ${firstCol} > <max>;`
        : `SELECT ${colList} FROM ${table};`
    case 'referential_integrity':
    case 'foreign_key':
      return firstCol
        ? `-- Referential integrity: orphan rows in ${table}\nSELECT t.${colList}\nFROM ${table} t\nLEFT JOIN <parent_table> p ON t.${firstCol} = p.<parent_key>\nWHERE p.<parent_key> IS NULL;`
        : `SELECT ${colList} FROM ${table};`
    case 'freshness':
      return `-- Freshness: most recent timestamp in ${table}\nSELECT MAX(updated_at) AS last_updated, NOW() - MAX(updated_at) AS staleness\nFROM ${table};`
    case 'schema_drift':
      return `-- Schema drift: compare current schema against expected\nSELECT column_name, data_type, is_nullable\nFROM information_schema.columns\nWHERE table_name = '${nr.table_name || 'target_table'}'${nr.schema_name ? ` AND table_schema = '${nr.schema_name}'` : ''};`
    default:
      return `-- Generic check on ${table}\nSELECT ${colList}\nFROM ${table};`
  }
}

function ViolationsList({ violations }: { violations: Array<Record<string, unknown>> }) {
  if (violations.length === 0) {
    return (
      <p className="text-sm text-content-muted" data-testid="evidence-no-violations">
        No structured violations were recorded for this check.
      </p>
    )
  }
  return (
    <ul className="space-y-1.5" data-testid="evidence-violations-list">
      {violations.map((v, i) => (
        <li
          key={i}
          className="rounded-md border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-danger"
          data-testid={`violation-${i}`}
        >
          <code className="break-words font-mono">{JSON.stringify(v)}</code>
        </li>
      ))}
    </ul>
  )
}

function SampleTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = useMemo(() => {
    const set = new Set<string>()
    rows.forEach((r) => Object.keys(r).forEach((k) => set.add(k)))
    return Array.from(set)
  }, [rows])

  if (rows.length === 0) {
    return (
      <p className="text-sm text-content-muted" data-testid="evidence-no-sample">
        No sample rows were captured for this run.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto rounded-md border border-edge" data-testid="evidence-sample-table">
      <table className="min-w-full text-xs">
        <thead className="bg-surface text-content-muted">
          <tr>
            {columns.map((c) => (
              <th key={c} className="px-2 py-1 text-left font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-edge-subtle">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1 text-content">
                  {r[c] == null ? <span className="text-content-subtle">null</span> : String(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function EvidencePanel({ nodeResult }: Props) {
  const sql = useMemo(() => synthesizeSql(nodeResult), [nodeResult])
  const [activeTab, setActiveTab] = useState<'sql' | 'violations' | 'sample'>('sql')

  const copySql = async () => {
    try {
      await navigator.clipboard.writeText(sql)
      toast.success('SQL copied to clipboard')
    } catch {
      toast.error('Failed to copy SQL')
    }
  }

  const violationCount = nodeResult.violations?.length ?? 0
  const sampleCount = nodeResult.sample_data?.length ?? 0

  const tabs: Array<{ id: 'sql' | 'violations' | 'sample'; label: string; icon: typeof Code2; count?: number }> = [
    { id: 'sql', label: 'Generated SQL', icon: Code2 },
    { id: 'violations', label: 'Violations', icon: AlertTriangle, count: violationCount },
    { id: 'sample', label: 'Sample rows', icon: Table, count: sampleCount },
  ]

  return (
    <div
      className="rounded-2xl border border-edge bg-surface-raised p-4"
      data-testid="evidence-panel"
    >
      <div className="mb-3 flex items-center gap-2">
        <Code2 className="h-4 w-4 text-content-muted" />
        <h3 className="text-sm font-semibold text-content">Evidence</h3>
        {nodeResult.check_type ? (
          <span className="ml-1 rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-brand">
            {nodeResult.check_type}
          </span>
        ) : null}
        {nodeResult.threshold ? (
          <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] text-content-muted">
            threshold {nodeResult.threshold}
          </span>
        ) : null}
      </div>

      <div role="tablist" aria-label="Evidence views" className="mb-3 flex gap-1 overflow-x-auto border-b border-edge">
        {tabs.map((t, idx) => {
          const Icon = t.icon
          const active = activeTab === t.id
          return (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              aria-controls={`evidence-panel-${t.id}`}
              id={`evidence-tabbtn-${t.id}`}
              data-testid={`evidence-tab-${t.id}`}
              onClick={() => setActiveTab(t.id)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                  e.preventDefault()
                  const dir = e.key === 'ArrowRight' ? 1 : -1
                  const next = tabs[(idx + dir + tabs.length) % tabs.length]
                  setActiveTab(next.id)
                  const el = document.querySelector<HTMLElement>(
                    `[data-testid="evidence-tab-${next.id}"]`,
                  )
                  el?.focus()
                }
              }}
              className={`-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-xs font-medium transition-colors ${
                active
                  ? 'border-brand text-brand'
                  : 'border-transparent text-content-muted hover:text-content'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
              {typeof t.count === 'number' && t.count > 0 ? (
                <span className="ml-1 rounded-full bg-surface px-1.5 text-[10px] text-content-muted">
                  {t.count}
                </span>
              ) : null}
            </button>
          )
        })}
      </div>

      {activeTab === 'sql' ? (
        <div role="tabpanel" id="evidence-panel-sql" aria-labelledby="evidence-tabbtn-sql">
          <div className="mb-2 flex items-center justify-end">
            <button
              type="button"
              onClick={copySql}
              data-testid="evidence-copy-sql"
              className="inline-flex items-center gap-1.5 rounded-md border border-edge bg-surface px-2.5 py-1 text-xs text-content hover:bg-surface-overlay"
            >
              <Copy className="h-3.5 w-3.5" />
              Copy
            </button>
          </div>
          <pre
            data-testid="evidence-sql"
            className="overflow-x-auto rounded-md border border-edge bg-surface p-3 font-mono text-xs leading-relaxed text-content"
          >
            <code>{sql}</code>
          </pre>
          <p className="mt-2 text-[11px] text-content-subtle">
            Representation of the predicate evaluated by the engine. Dialect may vary.
          </p>
        </div>
      ) : null}

      {activeTab === 'violations' ? (
        <div role="tabpanel" id="evidence-panel-violations" aria-labelledby="evidence-tabbtn-violations">
          <ViolationsList violations={nodeResult.violations || []} />
        </div>
      ) : null}

      {activeTab === 'sample' ? (
        <div role="tabpanel" id="evidence-panel-sample" aria-labelledby="evidence-tabbtn-sample">
          <SampleTable rows={nodeResult.sample_data || []} />
        </div>
      ) : null}
    </div>
  )
}
