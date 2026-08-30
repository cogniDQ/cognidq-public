/**
 * Auto-slug generator for tenant creation.
 *
 * Mirrors the slug normalization rules from TDD §6.2:
 * - Lowercase
 * - Spaces → hyphens
 * - Strip non-[a-z0-9-] characters
 * - Collapse consecutive hyphens into one
 * - Strip leading and trailing hyphens
 */
export function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '');
}
