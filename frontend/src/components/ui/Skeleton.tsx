import type { CSSProperties } from 'react';

interface SkeletonProps {
  /** Tailwind width class, e.g. "w-24" or "w-full". Defaults to "w-full". */
  width?: string;
  /** Tailwind height class, e.g. "h-4". Defaults to "h-4". */
  height?: string;
  /** Tailwind rounded class. Defaults to "rounded". */
  rounded?: string;
  className?: string;
  style?: CSSProperties;
}

/**
 * Basic shimmer placeholder. Compose into table rows, cards, etc.
 */
export function Skeleton({
  width = 'w-full',
  height = 'h-4',
  rounded = 'rounded',
  className = '',
  style,
}: SkeletonProps) {
  return (
    <div
      aria-hidden
      style={style}
      className={`animate-pulse bg-edge ${width} ${height} ${rounded} ${className}`}
    />
  );
}

interface SkeletonTextProps {
  lines?: number;
  className?: string;
}

/** Multi-line text placeholder. */
export function SkeletonText({ lines = 3, className = '' }: SkeletonTextProps) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="h-3"
          width={i === lines - 1 ? 'w-3/5' : 'w-full'}
        />
      ))}
    </div>
  );
}

interface SkeletonRowsProps {
  rows?: number;
  columns?: number;
  className?: string;
}

/** Table-row placeholder. Drop into a tbody. */
export function SkeletonRows({ rows = 5, columns = 4, className = '' }: SkeletonRowsProps) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r} className={className}>
          {Array.from({ length: columns }).map((__, c) => (
            <td key={c} className="px-4 py-3">
              <Skeleton height="h-3" width={c === 0 ? 'w-32' : 'w-20'} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default Skeleton;
