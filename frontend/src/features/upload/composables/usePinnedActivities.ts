import { shallowReactive } from 'vue'
import type { InfiniteData } from '@tanstack/vue-query'

import { fetchActivity } from '@/features/activities/services/activities'
import type { ActivityFeedSlice, ActivitySummary } from '@/features/activities/types'

/**
 * Activities uploaded in this session, kept at the top of the viewer's home feed.
 *
 * Module-level state on purpose: the upload that pins an activity and the feed
 * query that must keep showing it first are different components, and a refetch
 * (a realtime event, a focus refetch) replaces the feed cache with the server's
 * date ordering. Nothing persists, so a reload restores the server ordering.
 * Insertion order is upload order, oldest first.
 */
const pinned = shallowReactive(new Map<string, ActivitySummary>())

/**
 * Pins freshly uploaded activities to the top of the home feed.
 *
 * @param activities - The newly created activities.
 * @returns Nothing.
 */
export function pinActivities(activities: ActivitySummary[]): void {
  for (const activity of activities) {
    pinned.set(activity.id, activity)
  }
}

/**
 * Drops an activity's pin, e.g. because it was deleted.
 *
 * @param activityId - The activity to stop pinning.
 * @returns Nothing.
 */
export function unpinActivity(activityId: string): void {
  pinned.delete(activityId)
}

/**
 * Swaps refreshed copies in for activities that are pinned, keeping their pin.
 *
 * @param activities - The refreshed activities; those not pinned are ignored.
 * @returns Nothing.
 */
export function updatePinnedActivities(activities: ActivitySummary[]): void {
  for (const activity of activities) {
    if (pinned.has(activity.id)) {
      pinned.set(activity.id, activity)
    }
  }
}

/**
 * Re-reads every pinned activity from the server, so a pinned card keeps up with
 * what the background jobs add after the upload (map thumbnail, location) even
 * when the activity is too old to be on a loaded feed page. An activity the
 * server no longer has is unpinned; a failed read keeps the stored copy.
 *
 * @returns A promise resolving once every pinned activity has been re-read.
 */
export async function refreshPinnedActivities(): Promise<void> {
  await Promise.all(
    [...pinned.keys()].map(async (id) => {
      try {
        const fresh = await fetchActivity(id)
        if (fresh === null) {
          unpinActivity(id)
        } else {
          updatePinnedActivities([fresh])
        }
      } catch {
        // Keep the stored copy; the next refetch tries again.
      }
    }),
  )
}

/**
 * Returns a copy of the home-feed value with every pinned activity moved to the
 * top of the first page, newest upload first. The feed's own copy of a pinned
 * activity is preferred over the stored one, so a refetch that carries newer
 * data (a thumbnail that landed late) is not masked; the stored copy is used
 * only when the feed has not loaded that row. Feed copies are removed from their
 * pages so the pin can't produce duplicate rows.
 * Pure and immutable — never mutates in place.
 *
 * @param data - The cached infinite-feed value, or `undefined` when unpopulated.
 * @returns The feed with the pins on top, or `data` itself when nothing is pinned.
 */
export function floatPinnedActivities(
  data: InfiniteData<ActivityFeedSlice> | undefined,
): InfiniteData<ActivityFeedSlice> | undefined {
  if (!data || data.pages.length === 0 || pinned.size === 0) {
    return data
  }
  const fresh = new Map(
    data.pages.flatMap((slice) => slice.items).map((activity) => [activity.id, activity]),
  )
  const top = [...pinned.values()].reverse().map((activity) => fresh.get(activity.id) ?? activity)
  const [first, ...rest] = data.pages.map((slice) => ({
    ...slice,
    items: slice.items.filter((activity) => !pinned.has(activity.id)),
  }))
  return first ? { ...data, pages: [{ ...first, items: [...top, ...first.items] }, ...rest] } : data
}
