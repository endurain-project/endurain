import maleAvatar from '@/assets/avatar/male1.png'
import femaleAvatar from '@/assets/avatar/female1.png'
import unspecifiedAvatar from '@/assets/avatar/unspecified1.png'

/**
 * Maps gender identifiers to their corresponding default avatar image paths.
 *
 * @remarks
 * Gender mappings:
 * - **1**: Male avatar
 * - **2**: Female avatar
 * - **3**: Unspecified/neutral avatar
 */
export const USER_AVATAR_MAP: Record<number, string> = {
    1: maleAvatar,
    2: femaleAvatar,
    3: unspecifiedAvatar
} as const

/**
 * Retrieves the default avatar image path for a given gender.
 *
 * @param gender - The numeric gender identifier (1-3). Optional.
 * @returns The avatar image path corresponding to the gender, or the male avatar as default.
 *
 * @remarks
 * Returns male avatar if gender is undefined, null, or out of range (< 1 or > 3).
 * Falls back to unspecified avatar if the gender value is not found in the map.
 */
export function getUserDefaultAvatar(gender?: number): string {
    if (!gender || gender < 1 || gender > 3) {
        return maleAvatar // Default to male avatar
    }
    return USER_AVATAR_MAP[gender] ?? unspecifiedAvatar
}
