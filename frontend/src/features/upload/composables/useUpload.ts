import { type InfiniteData, useMutation, useQueryClient } from '@tanstack/vue-query'

import { fetchActivity, mapActivity } from '@/features/activities/services/activities'
import type { Activity } from '@/features/activities/types'
import { uploadActivityFile } from '@/features/upload/services/upload'
import type { Activity as UploadedActivity } from '@/features/upload/types'
import { queryKeys } from '@/services/queryKeys'

/**
 * Reads the `scope` tag from an activities list query key, when the key carries
 * a serialized filters object (the home feeds and list views do; broader
 * prefixes do not).
 *
 * @param queryKey - The query key to inspect.
 * @returns The `scope` string, or `undefined` when the key carries none.
 */
function activityListScope(queryKey: readonly unknown[]): string | undefined {
  const filters = queryKey[2]
  if (filters && typeof filters === 'object' && 'scope' in filters) {
    const scope = (filters as { scope?: unknown }).scope
    return typeof scope === 'string' ? scope : undefined
  }
  return undefined
}

/**
 * Returns a copy of the home-feed cache with the freshly uploaded activities
 * pinned to the very top of the first page. Any existing copies (e.g. from a
 * background refetch that already placed them) are removed first so the pin
 * can't produce duplicate rows. Pure and immutable — never mutates in place.
 *
 * @param data - The cached infinite-feed value, or `undefined` when unpopulated.
 * @param activities - The newly created activities to pin to the top.
 * @returns The updated feed value, or `undefined` when there was nothing cached.
 */
export function prependActivitiesToFeed(
  data: InfiniteData<Activity[]> | undefined,
  activities: Activity[],
): InfiniteData<Activity[]> | undefined {
  if (!data || data.pages.length === 0 || activities.length === 0) {
    return data
  }
  const newIds = new Set(activities.map((activity) => activity.id))
  const dedupedPages = data.pages.map((page) => page.filter((activity) => !newIds.has(activity.id)))
  const firstPage = dedupedPages[0] ?? []
  return {
    ...data,
    pages: [[...activities, ...firstPage], ...dedupedPages.slice(1)],
  }
}

/**
 * Write-path reference for file uploads: a TanStack mutation that uploads one
 * activity file and reconciles the activities cache once the server responds.
 *
 * The upload response is serialized before the backend generates the map
 * thumbnail, so it never carries `map_thumbnail_path`. Each created activity is
 * therefore re-fetched (the thumbnail is already persisted by the time the OK
 * comes back) and the complete, server-authoritative row is optimistically
 * pinned to the top of the viewer's home feed (see {@link prependActivitiesToFeed})
 * so a fresh upload is immediately visible — with its map — instead of buried in
 * its chronological position. `onSuccess` is awaited, so the mutation stays
 * pending (and the feed's upload placeholder stays up) until the reconciliation
 * finishes.
 *
 * The home feeds are deliberately excluded from the settle-time invalidation —
 * refetching them would reorder the new activity out of view before the viewer
 * notices it; a full reload restores the server-authoritative ordering. Every
 * other activities query (stats, counts, summaries, list views) still refetches
 * so those stay authoritative.
 *
 * @returns The TanStack mutation. Call `mutate(file)` / `mutateAsync(file)`.
 */
export function useUploadActivityFileMutation() {
  const queryClient = useQueryClient()

  return useMutation<UploadedActivity[], Error, File>({
    mutationFn: (file) => uploadActivityFile(file),
    onSuccess: async (createdActivities) => {
      // Re-fetch each created activity so the pinned row includes its map
      // thumbnail (absent from the upload response); fall back to the upload
      // payload if a re-fetch fails so an activity is still pinned.
      const created = await Promise.all(
        createdActivities.map(async (dto) => {
          if (typeof dto.id === 'number' && dto.id > 0) {
            const fresh = await fetchActivity(dto.id, { authenticated: true }).catch(() => null)
            if (fresh) {
              return fresh
            }
          }
          return mapActivity(dto)
        }),
      )
      if (created.length === 0) {
        return
      }
      // Pin the new activities to the top of the viewer's own feed ("user-feed"
      // scope). The followers feed never contains the viewer's own uploads.
      queryClient.setQueriesData<InfiniteData<Activity[]>>(
        {
          queryKey: queryKeys.activities.lists(),
          predicate: (query) => activityListScope(query.queryKey) === 'user-feed',
        },
        (data) => prependActivitiesToFeed(data, created),
      )
    },
    onSettled: () => {
      // Refresh every activities query except the home feeds, which were just
      // updated by hand; refetching them would drop the new activity from the
      // top before the viewer sees it (a reload restores server ordering).
      void queryClient.invalidateQueries({
        queryKey: queryKeys.activities.all(),
        predicate: (query) => {
          const scope = activityListScope(query.queryKey)
          return scope !== 'user-feed' && scope !== 'followers-feed'
        },
      })
    },
  })
}
