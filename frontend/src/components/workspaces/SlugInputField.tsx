/**
 * SlugInputField — controlled input for the workspace URL slug.
 *
 * Per P10 spec:
 * - Per-keystroke: detects characters outside [a-z0-9-] and displays an
 *   inline warning (not a hard error — lets user keep typing).
 * - On blur or submit attempt: detects slug  < 3 chars and shows error.
 * - Accepts `isAutoPopulated` prop — while auto-population is active (before
 *   user interacts) errors are suppressed to avoid premature feedback.
 * - Static slug immutability notice always visible.
 *
 * Edge case (EC-6): if the derived value is empty (all-invalid chars stripped),
 * the parent passes an empty string; the blur/submit error informs the user
 * that the name must contain at least one valid character.
 */
import { detectSlugInvalidChars } from '../../utils/workspaceValidation';

interface SlugInputFieldProps {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
  /** Suppresses character and length warnings while slug is auto-populated
   * before the user has interacted with the field. */
  isAutoPopulated?: boolean;
}

const ID = 'workspace-slug';
const INVALID_CHAR_WARNING =
  'Slug may only contain lowercase letters, digits, and hyphens.';

export default function SlugInputField({
  value,
  onChange,
  onBlur,
  error,
  isAutoPopulated = false,
}: SlugInputFieldProps) {
  const showInvalidCharWarning = !isAutoPopulated && detectSlugInvalidChars(value);

  return (
    <div className="space-y-1.5">
      <label htmlFor={ID} className="block text-sm font-medium text-gray-300">
        Slug <span className="text-red-400" aria-hidden="true">*</span>
      </label>
      <input
        id={ID}
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        maxLength={85}
        className={`w-full rounded-lg bg-dark-800/60 border px-3 py-2.5 text-sm text-gray-100 font-mono placeholder-gray-600 outline-none transition-colors focus:ring-2 focus:ring-primary-500/50 ${
          error ? 'border-red-500/60' : 'border-dark-700/60 focus:border-primary-500/50'
        }`}
        placeholder="e.g. my-workspace"
        aria-required="true"
        aria-describedby={
          [
            error ? `${ID}-error` : '',
            showInvalidCharWarning ? `${ID}-char-warning` : '',
            `${ID}-notice`,
          ]
            .filter(Boolean)
            .join(' ') || undefined
        }
        data-testid="field-workspace-slug"
      />

      {/* Hard error (blur / submit): length < 3 or format violation */}
      {error && (
        <p
          id={`${ID}-error`}
          className="text-xs text-red-400"
          role="alert"
          data-testid="error-workspace-slug"
        >
          {error}
        </p>
      )}

      {/* Per-keystroke invalid character warning (softer) */}
      {!error && showInvalidCharWarning && (
        <p
          id={`${ID}-char-warning`}
          className="text-xs text-amber-400"
          role="alert"
          data-testid="slug-invalid-char-warning"
        >
          {INVALID_CHAR_WARNING}
        </p>
      )}

      {/* Slug immutability notice — always visible */}
      <p
        id={`${ID}-notice`}
        className="text-xs text-amber-500/80"
        data-testid="slug-immutability-notice"
      >
        <span className="font-medium">Cannot be changed after creation.</span> Choose
        carefully — the slug is a permanent identifier for this workspace.
      </p>
    </div>
  );
}
