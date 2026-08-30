/**
 * E4 — Direct field editor for the parsed SIR.
 *
 * Lets the user fix small mistakes in the parsed rule without re-running the
 * NL parser. Edits are local (mutating the parseResult held in NLRuleBuilder)
 * and persist when the user advances to Step 3 / submits.
 */
import { useState } from 'react'
import { Pencil, Save, X } from 'lucide-react'
import type {
  ParseRuleResponse,
  StructuredIntermediateRepresentation,
  SIREntity,
  SIRCondition,
} from '@/types/nlRuleBuilder'

interface SIRFieldEditorProps {
  parseResult: ParseRuleResponse
  onChange: (next: ParseRuleResponse) => void
}

function cloneEntity(e: SIREntity): SIREntity {
  return { ...e }
}

function cloneCondition(c: SIRCondition): SIRCondition {
  return { ...c, field: cloneEntity(c.field) }
}

function cloneSIR(
  sir: StructuredIntermediateRepresentation,
): StructuredIntermediateRepresentation {
  return {
    ...sir,
    subject: cloneEntity(sir.subject),
    object: sir.object ? cloneEntity(sir.object) : null,
    scope: sir.scope ? { ...sir.scope } : undefined,
    conditions: sir.conditions.map(cloneCondition),
    constraints: [...sir.constraints],
    parse_warnings: [...sir.parse_warnings],
  }
}

export default function SIRFieldEditor({
  parseResult,
  onChange,
}: SIRFieldEditorProps) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<StructuredIntermediateRepresentation | null>(
    null,
  )

  const sir = parseResult.parsed_rule
  if (!sir) return null

  function startEdit() {
    setDraft(cloneSIR(sir!))
    setOpen(true)
  }

  function cancel() {
    setDraft(null)
    setOpen(false)
  }

  function save() {
    if (!draft) return
    onChange({ ...parseResult, parsed_rule: draft })
    setOpen(false)
    setDraft(null)
  }

  function patchDraft(
    partial: Partial<StructuredIntermediateRepresentation>,
  ) {
    setDraft((d) => (d ? { ...d, ...partial } : d))
  }

  function patchSubject(partial: Partial<SIREntity>) {
    setDraft((d) =>
      d ? { ...d, subject: { ...d.subject, ...partial } } : d,
    )
  }

  function patchObject(partial: Partial<SIREntity>) {
    setDraft((d) =>
      d
        ? { ...d, object: { ...(d.object ?? { raw_text: '' }), ...partial } }
        : d,
    )
  }

  function patchCondition(idx: number, partial: Partial<SIRCondition>) {
    setDraft((d) => {
      if (!d) return d
      const conds = d.conditions.slice()
      conds[idx] = { ...conds[idx], ...partial }
      return { ...d, conditions: conds }
    })
  }

  function patchConditionField(idx: number, partial: Partial<SIREntity>) {
    setDraft((d) => {
      if (!d) return d
      const conds = d.conditions.slice()
      conds[idx] = {
        ...conds[idx],
        field: { ...conds[idx].field, ...partial },
      }
      return { ...d, conditions: conds }
    })
  }

  if (!open) {
    return (
      <div className="flex justify-end">
        <button
          type="button"
          onClick={startEdit}
          className="inline-flex items-center gap-1 text-xs text-primary-300 hover:text-primary-200"
          data-testid="sir-edit-toggle"
        >
          <Pencil className="w-3.5 h-3.5" />
          Edit fields directly
        </button>
      </div>
    )
  }

  const d = draft!

  return (
    <div
      className="card border border-primary-500/30"
      data-testid="sir-field-editor"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-100 flex items-center gap-2">
          <Pencil className="w-4 h-4 text-primary-400" />
          Edit parsed fields
        </h3>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={cancel}
            className="btn btn-secondary text-xs flex items-center gap-1"
            data-testid="sir-cancel-btn"
          >
            <X className="w-3.5 h-3.5" />
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            className="btn btn-primary text-xs flex items-center gap-1"
            data-testid="sir-save-btn"
          >
            <Save className="w-3.5 h-3.5" />
            Save
          </button>
        </div>
      </div>

      <p className="text-xs text-gray-400 mb-3">
        Adjust parsed fields directly. The parser is not re-run — only your
        edits apply.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <Field label="Subject (column)">
          <input
            type="text"
            value={d.subject.raw_text}
            onChange={(e) => patchSubject({ raw_text: e.target.value })}
            className="input w-full"
            data-testid="sir-subject"
          />
        </Field>

        <Field label="Operator">
          <input
            type="text"
            value={d.operator ?? ''}
            onChange={(e) => patchDraft({ operator: e.target.value || null })}
            className="input w-full"
            data-testid="sir-operator"
            placeholder="e.g. is_not_null, greater_than, in_list"
          />
        </Field>

        <Field label="Object / value">
          <input
            type="text"
            value={d.object?.raw_text ?? ''}
            onChange={(e) =>
              e.target.value === ''
                ? patchDraft({ object: null })
                : patchObject({ raw_text: e.target.value })
            }
            className="input w-full"
            data-testid="sir-object"
            placeholder="leave empty for unary operators"
          />
        </Field>

        <Field label="Pass threshold (%)">
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={d.threshold_pass ?? ''}
            onChange={(e) =>
              patchDraft({
                threshold_pass:
                  e.target.value === '' ? null : Number(e.target.value),
              })
            }
            className="input w-full"
            data-testid="sir-threshold-pass"
          />
        </Field>

        <Field label="Warn threshold (%)">
          <input
            type="number"
            min={0}
            max={100}
            step="0.01"
            value={d.threshold_warn ?? ''}
            onChange={(e) =>
              patchDraft({
                threshold_warn:
                  e.target.value === '' ? null : Number(e.target.value),
              })
            }
            className="input w-full"
            data-testid="sir-threshold-warn"
          />
        </Field>

        <Field label="Inline severity">
          <select
            value={d.inline_severity ?? ''}
            onChange={(e) =>
              patchDraft({ inline_severity: e.target.value || null })
            }
            className="input w-full"
            data-testid="sir-severity"
          >
            <option value="">(unset)</option>
            <option value="critical">critical</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </Field>
      </div>

      {d.conditions.length > 0 && (
        <div className="mt-4">
          <div className="text-xs font-semibold text-gray-300 mb-2">
            Conditions
          </div>
          <div className="space-y-2">
            {d.conditions.map((c, i) => (
              <div
                key={i}
                className="grid grid-cols-1 md:grid-cols-3 gap-2 rounded border border-dark-700 px-2 py-2"
                data-testid={`sir-condition-${i}`}
              >
                <input
                  type="text"
                  value={c.field.raw_text}
                  onChange={(e) =>
                    patchConditionField(i, { raw_text: e.target.value })
                  }
                  className="input"
                  placeholder="field"
                />
                <input
                  type="text"
                  value={c.operator}
                  onChange={(e) =>
                    patchCondition(i, { operator: e.target.value })
                  }
                  className="input"
                  placeholder="operator"
                />
                <input
                  type="text"
                  value={
                    c.value === undefined || c.value === null
                      ? ''
                      : String(c.value)
                  }
                  onChange={(e) =>
                    patchCondition(i, {
                      value: e.target.value === '' ? undefined : e.target.value,
                    })
                  }
                  className="input"
                  placeholder="value"
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-[11px] uppercase tracking-wide text-gray-500 mb-1 block">
        {label}
      </span>
      {children}
    </label>
  )
}
