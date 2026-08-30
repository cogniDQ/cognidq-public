import { Moon, Sun, MonitorSmartphone } from 'lucide-react';
import { useTheme, type ThemeMode } from './ThemeContext';

interface ThemeToggleProps {
  /** Compact button (toggles light/dark only). Default true. */
  compact?: boolean;
  className?: string;
}

/**
 * Compact icon button that flips between light and dark.
 * Use `compact={false}` to render a 3-way segmented control (system/light/dark).
 */
export function ThemeToggle({ compact = true, className }: ThemeToggleProps) {
  const { mode, resolved, setMode, toggle } = useTheme();

  if (compact) {
    const isDark = resolved === 'dark';
    return (
      <button
        type="button"
        onClick={toggle}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        data-testid="theme-toggle"
        className={
          className ??
          'inline-flex h-9 w-9 items-center justify-center rounded text-gray-400 hover:bg-gray-700 hover:text-white transition-colors'
        }
      >
        {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
    );
  }

  const options: Array<{ value: ThemeMode; label: string; icon: JSX.Element }> = [
    { value: 'system', label: 'System', icon: <MonitorSmartphone className="h-4 w-4" /> },
    { value: 'light', label: 'Light', icon: <Sun className="h-4 w-4" /> },
    { value: 'dark', label: 'Dark', icon: <Moon className="h-4 w-4" /> },
  ];

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className={
        className ??
        'inline-flex items-center gap-1 rounded-lg border border-edge bg-surface-raised p-1'
      }
    >
      {options.map((opt) => {
        const active = mode === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setMode(opt.value)}
            className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium transition-colors ${
              active
                ? 'bg-brand text-white shadow-sm'
                : 'text-content-muted hover:bg-edge-subtle hover:text-content'
            }`}
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default ThemeToggle;
