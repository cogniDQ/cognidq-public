/**
 * Brand logo component for CogniDQ.
 *
 * Variants:
 *   - 'full'  : full lockup with dark wordmark (use on light backgrounds)
 *   - 'light' : full lockup with light wordmark (use on dark backgrounds)
 *   - 'mark'  : icon-only mark (square)
 *
 * Sizing: pass `className` (e.g. "h-8 w-auto") or use the `size` prop preset.
 */

interface LogoProps {
  variant?: 'full' | 'light' | 'mark'
  className?: string
  alt?: string
}

const SRC: Record<NonNullable<LogoProps['variant']>, string> = {
  full: '/brand/logo.svg',
  light: '/brand/logo-light.svg',
  mark: '/brand/logo-mark.svg',
}

export default function Logo({ variant = 'light', className = 'h-8 w-auto', alt = 'CogniDQ' }: LogoProps) {
  return <img src={SRC[variant]} alt={alt} className={className} draggable={false} />
}
