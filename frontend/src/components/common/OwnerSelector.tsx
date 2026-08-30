/**
 * OwnerSelector
 * =============
 * Reusable dropdown that lets a workspace member be selected as the owner of a
 * rule, flow, incident, or any other entity. Fetches the member roster from
 * `GET /workspaces/{workspace_id}/members` (F078) and emits a user_id (or null
 * to unassign) when selection changes.
 *
 * Usage:
 *   <OwnerSelector
 *     workspaceId={ws}
 *     value={rule.owner_user_id ?? null}
 *     onChange={(uid) => assignRuleOwner(ws, rule.id, uid)}
 *   />
 */
import { useEffect, useMemo, useState } from 'react'
import { api } from '@/services/api'

interface Member {
  user_id: string
  email: string
  display_name: string
  role_name: string
}

interface OwnerSelectorProps {
  workspaceId: string
  value: string | null
  onChange: (userId: string | null) => void | Promise<void>
  disabled?: boolean
  className?: string
  placeholder?: string
  allowUnassign?: boolean
}

export default function OwnerSelector({
  workspaceId,
  value,
  onChange,
  disabled = false,
  className = '',
  placeholder = 'Select owner…',
  allowUnassign = true,
}: OwnerSelectorProps) {
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .get(`/workspaces/${workspaceId}/members`)
      .then((res) => {
        if (cancelled) return
        const list: Member[] = res.data?.members ?? []
        setMembers(list)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err?.response?.data?.detail || 'Failed to load members')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const sortedMembers = useMemo(
    () =>
      [...members].sort((a, b) =>
        (a.display_name || a.email).localeCompare(b.display_name || b.email),
      ),
    [members],
  )

  const handleChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value === '' ? null : e.target.value
    await onChange(next)
  }

  return (
    <div className={className}>
      <select
        value={value ?? ''}
        onChange={handleChange}
        disabled={disabled || loading}
        className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-gray-50"
      >
        {allowUnassign && <option value="">{placeholder}</option>}
        {sortedMembers.map((m) => (
          <option key={m.user_id} value={m.user_id}>
            {m.display_name || m.email} · {m.role_name}
          </option>
        ))}
      </select>
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  )
}
