/**
 * User Avatar Constants
 *
 * Centralized constants for user avatar images by gender.
 * Maps gender types to their corresponding default avatar images.
 */

import maleAvatar from '@/assets/avatar/male1.png'
import femaleAvatar from '@/assets/avatar/female1.png'
import unspecifiedAvatar from '@/assets/avatar/unspecified1.png'

/**
 * User avatar mapping by gender
 * Maps gender IDs to their default avatar image paths
 */
export const USER_AVATAR_MAP: Record<number, string> = {
    1: maleAvatar,
    2: femaleAvatar,
    3: unspecifiedAvatar
} as const

/**
 * Get default avatar image for a specific gender
 * @param gender - The gender ID (1=male, 2=female, 3=unspecified)
 * @returns The default avatar image path
 */
export function getUserDefaultAvatar(gender?: number): string {
    if (!gender || gender < 1 || gender > 3) {
        return maleAvatar // Default to male avatar
    }
    return USER_AVATAR_MAP[gender] ?? unspecifiedAvatar
}
