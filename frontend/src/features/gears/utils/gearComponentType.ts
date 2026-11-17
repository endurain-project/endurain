import { GEAR_TYPE } from '@/features/gears/utils/gearType'
import type { GearComponentTypeLists, GearType } from '@/features/gears/types'

/** The component-catalogue families exposed by the backend, by gear family. */
export type ComponentTypeListKey = keyof GearComponentTypeLists

/**
 * Maps a gear type to its component-catalogue key, or `null` when the
 * gear family tracks no components (wetsuits, skis, snowboards, boards).
 *
 * @param gearType - The gear type.
 * @returns The catalogue key, or `null` when the family has no components.
 */
export function componentTypeListKey(gearType: GearType): ComponentTypeListKey | null {
  switch (gearType) {
    case GEAR_TYPE.BICYCLE:
      return 'bike'
    case GEAR_TYPE.SHOES:
      return 'shoes'
    case GEAR_TYPE.RACQUET:
      return 'racquet'
    case GEAR_TYPE.WINDSURF:
      return 'windsurf'
    default:
      return null
  }
}

/**
 * Whether a gear family supports components (and so should offer "add").
 *
 * @param gearType - The gear type.
 * @returns `true` when the family has a component catalogue.
 */
export function gearTypeSupportsComponents(gearType: GearType): boolean {
  return componentTypeListKey(gearType) !== null
}

/**
 * Whether a gear family tracks component wear by **time** (the racquet family)
 * rather than by **distance** (every other family).
 *
 * @param gearType - The gear type.
 * @returns `true` when wear is measured in time, `false` for distance.
 */
export function isTimeBasedGear(gearType: GearType): boolean {
  return gearType === GEAR_TYPE.RACQUET
}

/**
 * Humanizes a snake_case component-type id into a sentence-case label, fixing
 * the catalogue's `break` spelling to `brake` (e.g. `front_break_pads` →
 * `Front brake pads`).
 *
 * @param type - The component-type id from the backend catalogue.
 * @returns A display label.
 */
export function humanizeComponentType(type: string): string {
  const words = type.split('_').map((word) => (word === 'break' ? 'brake' : word))
  const joined = words.join(' ').trim()
  return joined.length > 0 ? joined.charAt(0).toUpperCase() + joined.slice(1) : type
}

/**
 * Computes a component's wear as a whole-number percentage of its expected
 * lifespan. Both arguments must already be in the same base unit (metres for
 * distance gears, seconds for the racquet family), so this is a unit-agnostic
 * ratio.
 *
 * @param currentBaseUnits - Accumulated usage in base units (metres/seconds).
 * @param expectedBaseUnits - The wear threshold in base units, or `null`.
 * @returns The wear percentage (≥ 0, may exceed 100), or `null` when no
 *   threshold is set or it is non-positive.
 */
export function componentWearPercent(
  currentBaseUnits: number,
  expectedBaseUnits: number | null,
): number | null {
  if (expectedBaseUnits === null || expectedBaseUnits <= 0) {
    return null
  }
  return Math.round((currentBaseUnits / expectedBaseUnits) * 100)
}
