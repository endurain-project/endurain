import type { BristolType } from '@/features/health/types'

/**
 * The number of a Bristol Stool Scale type, as the scale names it.
 *
 * @param type - The backend Bristol type (`type_1` … `type_7`).
 * @returns The scale number, 1–7.
 */
export function bristolNumber(type: BristolType): number {
  return Number(type.slice('type_'.length))
}
