/**
 * ExpressionEditor — Multi-line monospace textarea (3-8 rows auto-expand)
 */
import { useRef, useEffect, useState } from 'react'
import { CheckCircle, XCircle } from 'lucide-react'

// Mirror of backend's _validate_filter_expression forbidden-construct check
const FORBIDDEN_PATTERN = /\b(DROP|ALTER|CREATE|INSERT|UPDATE|DELETE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|UNION|INTO)\b|;|\bSELECT\b.*\bFROM\b/i

/**
 * Replace string literals and double-quoted identifiers with a neutral token
 * so subsequent regex checks don't false-positive on their content.
 * Handles '' and "" as escape sequences inside their respective delimiters.
 */
function maskLiterals(expr: string): string {
  let out = ''
  let i = 0
  while (i < expr.length) {
    if (expr[i] === "'") {
      out += 'X'
      i++
      while (i < expr.length) {
        if (expr[i] === "'" && expr[i + 1] === "'") { i += 2 }       // '' escape
        else if (expr[i] === "'") { i++; break }                       // closing quote
        else { i++ }
      }
    } else if (expr[i] === '"') {
      out += 'X'
      i++
      while (i < expr.length) {
        if (expr[i] === '"' && expr[i + 1] === '"') { i += 2 }        // "" escape
        else if (expr[i] === '"') { i++; break }                       // closing quote
        else { i++ }
      }
    } else {
      out += expr[i++]
    }
  }
  return out
}

function validateExpressionSyntax(expr: string): string | null {
  const t = expr.trim()
  if (!t) return null

  // ── Phase 1: character-level walks (must run on raw string) ─────────────

  // 1. Unclosed single-quoted string literal ('' = escaped quote inside string)
  let inSQ = false
  for (let i = 0; i < t.length; i++) {
    if (t[i] === "'") {
      if (inSQ && t[i + 1] === "'") i++   // skip '' escape
      else inSQ = !inSQ
    }
  }
  if (inSQ) return "Unclosed string literal — missing closing quote (')"

  // 2. Unclosed double-quoted identifier ("" = escaped quote inside identifier)
  let inDQ = false
  for (let i = 0; i < t.length; i++) {
    if (t[i] === '"') {
      if (inDQ && t[i + 1] === '"') i++   // skip "" escape
      else inDQ = !inDQ
    }
  }
  if (inDQ) return 'Unclosed quoted identifier — missing closing double-quote (")'

  // 3. Unbalanced parentheses
  let depth = 0
  for (const ch of t) {
    if (ch === '(') depth++
    else if (ch === ')') depth--
    if (depth < 0) return 'Unexpected closing parenthesis'
  }
  if (depth > 0) return `Unclosed parenthesis — ${depth} opening parenthes${depth === 1 ? 'is' : 'es'} not closed`

  // ── Phase 2: token-level checks on masked string ─────────────────────────
  const m = maskLiterals(t)

  // 4. Common operator typos
  if (/=>/.test(m))  return 'Invalid operator "=>" — did you mean ">="?'
  if (/=</.test(m))  return 'Invalid operator "=<" — did you mean "<="?'
  if (/==/.test(m))  return 'Use "=" for equality comparisons, not "=="'

  // 5. Empty parentheses
  if (/\(\s*\)/.test(m)) return 'Empty parentheses "()" contain no expression'

  // 6. Starts with a binary or comparison operator (no left-hand operand)
  if (/^\s*(AND|OR)\b/i.test(m))   return 'Expression cannot start with AND or OR'
  if (/^\s*[=<>!*%/]/.test(m))     return 'Expression cannot start with a comparison or arithmetic operator'

  // 7. Ends with an operator
  //    Mask complete BETWEEN x AND y first so BETWEEN's own AND is invisible
  const mNB = m.replace(/\bBETWEEN\s+\S+\s+AND\s+\S+/gi, 'BETWEEN_RANGE')
  if (/\b(AND|OR)\s*$/i.test(mNB)) {
    const op = mNB.match(/\b(AND|OR)\s*$/i)![1].toUpperCase()
    return `Expression cannot end with ${op}`
  }
  if (/\b(NOT|LIKE|IS|IN|BETWEEN)\s*$/i.test(m)) {
    const op = m.match(/\b(NOT|LIKE|IS|IN|BETWEEN)\s*$/i)![1].toUpperCase()
    return `Expression cannot end with ${op}`
  }
  if (/[=<>!+\-*%/]\s*$/.test(m)) return 'Expression cannot end with an operator'

  // 8. Consecutive AND / OR (mask BETWEEN…AND portion only, keeping the 2nd value visible)
  const mNBA = m.replace(/\bBETWEEN\s+\S+\s+AND\b/gi, 'BETWEEN_EXPR')
  if (/\b(AND|OR)\s+(AND|OR)\b/i.test(mNBA)) {
    const match = mNBA.match(/\b(AND|OR)\s+(AND|OR)\b/i)!
    return `Consecutive "${match[1].toUpperCase()} ${match[2].toUpperCase()}" operators — missing operand between them`
  }

  // 9. Binary / comparison operator immediately after opening parenthesis
  if (/\(\s*(AND|OR)\b/i.test(m)) {
    const op = m.match(/\(\s*(AND|OR)\b/i)![1].toUpperCase()
    return `${op} cannot be the first token inside parentheses`
  }
  if (/\(\s*[=<>!]/.test(m)) return 'Comparison operator cannot be the first token inside parentheses'

  // 10. Operator immediately before closing parenthesis
  if (/\b(AND|OR|NOT|LIKE|IS|IN|BETWEEN)\s*\)/i.test(m)) {
    const op = m.match(/\b(AND|OR|NOT|LIKE|IS|IN|BETWEEN)\s*\)/i)![1].toUpperCase()
    return `"${op}" has no right-hand operand before ')'`
  }
  if (/[=<>!+\-*%/]\s*\)/.test(m)) return "Operator has no right-hand operand before ')'"

  // 11. IN / NOT IN must be followed by '('
  {
    const mi = m.replace(/\bNOT\s+IN\b/gi, '__NOTIN__')
    if (/\bIN\b(?!\s*\()/i.test(mi))
      return 'IN operator must be followed by a parenthesised list, e.g. col IN (val1, val2)'
  }

  // 12. Comparison chaining: a > b > c  (SQL does not support this; use AND or BETWEEN)
  if (/[<>!=]{1,2}\s*[\w.]+\s*[<>!=]{1,2}/.test(m))
    return 'Chained comparisons are not valid — use AND to combine conditions, or BETWEEN for ranges'

  return null
}

interface ExpressionEditorProps {
  value: string
  onChange: (value: string) => void
  label?: string
  placeholder?: string
  syntaxHint?: string
  minRows?: number
  maxRows?: number
  disabled?: boolean
}

export function ExpressionEditor({
  value,
  onChange,
  label,
  placeholder = 'Enter expression…',
  syntaxHint,
  minRows = 3,
  maxRows = 8,
  disabled = false,
}: ExpressionEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [validState, setValidState] = useState<'idle' | 'valid' | 'invalid'>('idle')
  const [validError, setValidError] = useState<string>('')

  // Auto-expand textarea
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return

    const lineHeight = 20 // approx monospace line height
    const minH = minRows * lineHeight
    const maxH = maxRows * lineHeight

    el.style.height = 'auto'
    const scrollH = el.scrollHeight
    el.style.height = `${Math.min(Math.max(scrollH, minH), maxH)}px`
  }, [value, minRows, maxRows])

  // Reset validation state whenever the expression changes
  useEffect(() => {
    setValidState('idle')
    setValidError('')
  }, [value])

  function handleValidate() {
    const expr = value.trim()
    if (!expr) {
      setValidState('invalid')
      setValidError('Expression cannot be empty')
      return
    }
    if (FORBIDDEN_PATTERN.test(expr)) {
      setValidState('invalid')
      setValidError('Expression contains forbidden SQL constructs (DROP, INSERT, SELECT…FROM, etc.)')
      return
    }
    const syntaxError = validateExpressionSyntax(expr)
    if (syntaxError) {
      setValidState('invalid')
      setValidError(syntaxError)
      return
    }
    setValidState('valid')
    setValidError('')
  }

  return (
    <div className="space-y-1">
      {label && (
        <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider">{label}</label>
      )}

      <textarea
        ref={textareaRef}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        rows={minRows}
        className="w-full bg-dark-900 border border-dark-700 rounded px-3 py-2 text-sm text-gray-200 font-mono placeholder-gray-600 focus:border-primary-500 focus:outline-none resize-none disabled:opacity-50"
      />

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleValidate}
          disabled={disabled || !value.trim()}
          className="text-xs px-2 py-1 rounded bg-dark-700 border border-dark-600 text-gray-300 hover:bg-dark-600 hover:text-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Validate Expression
        </button>

        {validState === 'valid' && (
          <span className="flex items-center gap-1 text-xs text-green-400">
            <CheckCircle className="w-3.5 h-3.5" />
            Valid
          </span>
        )}
        {validState === 'invalid' && (
          <span className="flex items-center gap-1 text-xs text-red-400">
            <XCircle className="w-3.5 h-3.5" />
            {validError}
          </span>
        )}
      </div>

      {syntaxHint && (
        <p className="text-xs text-gray-600">{syntaxHint}</p>
      )}
    </div>
  )
}
