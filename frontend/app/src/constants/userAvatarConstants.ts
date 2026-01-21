import maleAvatar from '@/assets/avatar/male1.png'
import femaleAvatar from '@/assets/avatar/female1.png'
import unspecifiedAvatar from '@/assets/avatar/unspecified1.png'

/**
 * Maps gender identifiers to their corresponding default avatar image paths.
 *
 * @remarks
 * Gender mappings:
 * - **male**: Male avatar
 * - **female**: Female avatar
 * - **unspecified**: Unspecified/neutral avatar
 */
export const USER_AVATAR_MAP: Record<string, string> = {
  male: maleAvatar,
  female: femaleAvatar,
  unspecified: unspecifiedAvatar
} as const

/**
 * Retrieves the default avatar image path for a given gender.
 *
 * @param gender - The gender identifier string ('male', 'female', 'unspecified'). Optional.
 * @returns The avatar image path corresponding to the gender, or the unspecified avatar as default.
 *
 * @remarks
 * Returns unspecified avatar if gender is undefined, null, or not found in the map.
 */
export function getUserDefaultAvatar(gender?: string): string {
  if (!gender) {
    return unspecifiedAvatar // Default to unspecified avatar
  }
  return USER_AVATAR_MAP[gender] ?? unspecifiedAvatar
}
