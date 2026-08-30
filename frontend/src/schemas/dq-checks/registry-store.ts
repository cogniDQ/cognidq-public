/**
 * Registry Store — leaf module, no circular dependencies.
 * 
 * Holds the dimension registry map and registerDimension().
 * Imported by dimension schema files so they can self-register
 * without creating a circular dependency with index.ts.
 */
import type { Dimension, DimensionSchema } from './types'

export const registry = new Map<Dimension, DimensionSchema>()

export function registerDimension(schema: DimensionSchema): void {
  registry.set(schema.dimension, schema)
}
