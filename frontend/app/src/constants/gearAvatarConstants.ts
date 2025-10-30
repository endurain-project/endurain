/**
 * Gear Avatar Constants
 *
 * Centralized constants for gear type avatar images.
 * Maps gear types to their corresponding avatar images.
 */

import bicycle1 from '@/assets/avatar/bicycle1.png'
import runningShoe1 from '@/assets/avatar/running_shoe1.png'
import wetsuit1 from '@/assets/avatar/wetsuit1.png'
import racquet1 from '@/assets/avatar/racquet1.png'
import skis1 from '@/assets/avatar/skis1.png'
import snowboard1 from '@/assets/avatar/snowboard1.png'
import windsurf1 from '@/assets/avatar/windsurf1.png'
import waterSportsBoard1 from '@/assets/avatar/waterSportsBoard1.png'

/**
 * Gear type avatar mapping
 * Maps gear type IDs to their avatar image paths
 */
export const GEAR_AVATAR_MAP: Record<number, string> = {
    1: bicycle1,
    2: runningShoe1,
    3: wetsuit1,
    4: racquet1,
    5: skis1,
    6: snowboard1,
    7: windsurf1,
    8: waterSportsBoard1
} as const

/**
 * Get avatar image for a specific gear type
 * @param gearType - The gear type ID (1-8)
 * @returns The avatar image path
 */
export function getGearAvatar(gearType: number): string {
    return GEAR_AVATAR_MAP[gearType] ?? bicycle1
}
