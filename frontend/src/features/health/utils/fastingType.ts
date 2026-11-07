import type { FastingType } from '@/features/health/types'

/**
 * Resolves the translated label of a fasting type.
 *
 * @param t - The vue-i18n translate function.
 * @param type - The fasting type.
 * @returns The label under `health.fasting.types.<type>`.
 */
export function fastingTypeLabel(t: (key: string) => string, type: FastingType): string {
  return t(`health.fasting.types.${type}`)
}
