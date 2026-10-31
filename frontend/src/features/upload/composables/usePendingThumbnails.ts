import { reactive } from 'vue'

/**
 * Activity ids whose map thumbnail is known to be still rendering server-side.
 *
 * Module-level (not component) state on purpose: the upload that registers an id
 * and the feed card that reads it are different components, and the card may
 * mount, unmount, and remount (navigation) while the thumbnail job is still
 * running. A `reactive` Set so `has()` is tracked by consuming computeds.
 *
 * Membership is a *positive* signal only — an activity absent from this set is
 * not "known to have no thumbnail", merely unknown. That distinction is what
 * keeps the loading hint off the many activities that legitimately never get a
 * thumbnail (no GPS track) and off older rows fetched in a normal feed page.
 */
const awaiting = reactive(new Set<number>())

/**
 * Marks activities as awaiting their map thumbnail.
 *
 * @param activityIds - Ids whose thumbnail is still being rendered.
 * @returns Nothing.
 */
export function markAwaitingThumbnail(activityIds: Iterable<number>): void {
  for (const id of activityIds) {
    awaiting.add(id)
  }
}

/**
 * Clears activities from the awaiting set, whether their thumbnail arrived or
 * the client gave up waiting for it.
 *
 * @param activityIds - Ids to stop awaiting.
 * @returns Nothing.
 */
export function clearAwaitingThumbnail(activityIds: Iterable<number>): void {
  for (const id of activityIds) {
    awaiting.delete(id)
  }
}

/**
 * Whether an activity's map thumbnail is known to be still rendering.
 *
 * @param activityId - The activity to check.
 * @returns `true` while the thumbnail is being awaited.
 */
export function isAwaitingThumbnail(activityId: number): boolean {
  return awaiting.has(activityId)
}
