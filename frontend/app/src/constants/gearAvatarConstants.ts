import bicycle1 from '@/assets/avatar/bicycle1.png'
import runningShoe1 from '@/assets/avatar/running_shoe1.png'
import wetsuit1 from '@/assets/avatar/wetsuit1.png'
import racquet1 from '@/assets/avatar/racquet1.png'
import skis1 from '@/assets/avatar/skis1.png'
import snowboard1 from '@/assets/avatar/snowboard1.png'
import windsurf1 from '@/assets/avatar/windsurf1.png'
import waterSportsBoard1 from '@/assets/avatar/waterSportsBoard1.png'
import unspecified1 from '@/assets/avatar/unspecified1.png'

/**
 * Maps gear type IDs to their corresponding avatar image paths.
 *
 * @remarks
 * The mapping includes:
 * - 1: Bicycle
 * - 2: Running shoe
 * - 3: Wetsuit
 * - 4: Racquet
 * - 5: Skis
 * - 6: Snowboard
 * - 7: Windsurf
 * - 8: Water sports board
 * - 9: Watch/Computer
 */
export const GEAR_AVATAR_MAP: Record<number, string> = {
  1: bicycle1,
  2: runningShoe1,
  3: wetsuit1,
  4: racquet1,
  5: skis1,
  6: snowboard1,
  7: windsurf1,
  8: waterSportsBoard1,
  9: unspecified1 // TODO: Replace with watch1.png when available
} as const

/**
 * Retrieves the avatar image path for a given gear type.
 *
 * @param gearType - The numeric identifier for the gear type.
 * @returns The image path for the specified gear type, or the default bicycle avatar if not found.
 */
export function getGearAvatar(gearType: number): string {
  return GEAR_AVATAR_MAP[gearType] ?? bicycle1
}
