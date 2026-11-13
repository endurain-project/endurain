import { toValue, type MaybeRefOrGetter } from 'vue'

/**
 * Resolves a reactive user id to its string.
 *
 * @param userId - Reactive id, or `null` while there is none.
 * @returns The id, or `''` when unavailable.
 */
export function resolveUserId(userId: MaybeRefOrGetter<string | null>): string {
  return toValue(userId) ?? ''
}
