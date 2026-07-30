import {
  type InfiniteData,
  type QueryClient,
  useMutation,
  useQueryClient,
} from '@tanstack/vue-query'

import { fetchActivity } from '@/features/activities/services/activities'
import type { Activity } from '@/features/activities/types'
import {
  clearAwaitingThumbnail,
  markAwaitingThumbnail,
} from '@/features/upload/composables/usePendingThumbnails'
import { fetchIngestionJob, uploadActivityFile } from '@/features/upload/services/upload'
import { type ActivityIngestionJob, isTerminalIngestionJob } from '@/features/upload/types'
import { queryKeys } from '@/services/queryKeys'

/** How long to wait between upload-job status polls. */
const POLL_INTERVAL_MS = 1500

/**
 * Delays before re-checking a freshly uploaded activity whose map thumbnail was
 * not ready yet. The thumbnail is rendered by a background job that finishes
 * *after* the upload job it reacted to, so the row fetched on completion can
 * legitimately still carry none. Bounded and give-up-quiet: a non-GPS activity
 * never gets one, and the hourly server-side backfill remains the real net.
 */
const THUMBNAIL_RETRY_DELAYS_MS = [2000, 5000, 10000]

/**
 * How long to keep polling before giving up. Generous because the wait covers
 * the queue as well as the parse: a large FIT file behind a backlog of other
 * uploads can legitimately take minutes.
 */
const POLL_TIMEOUT_MS = 5 * 60 * 1000

/**
 * Raised when an upload's background import finishes unsuccessfully, carrying
 * the server's sanitized reason so the UI can localize it.
 */
export class IngestionJobFailedError extends Error {
  /**
   * @param code - The server's sanitized failure reason, when it gave one.
   */
  constructor(readonly code: string | null | undefined) {
    super(`Activity import failed: ${code ?? 'unknown'}`)
    this.name = 'IngestionJobFailedError'
  }
}

/**
 * Raised when an upload job is still running after {@link POLL_TIMEOUT_MS}.
 * The import may still succeed server-side; only the client stopped watching.
 */
export class IngestionJobTimeoutError extends Error {
  constructor() {
    super('Timed out waiting for the activity import to finish.')
    this.name = 'IngestionJobTimeoutError'
  }
}

/**
 * Waits for a queued import to reach a terminal state.
 *
 * @param jobId - The job returned by the upload request.
 * @param options - Optional abort signal, polling interval, and timeout.
 * @returns The completed job.
 * @throws {IngestionJobFailedError} When the import finished unsuccessfully.
 * @throws {IngestionJobTimeoutError} When it is still running at the deadline.
 */
export async function pollIngestionJob(
  jobId: string,
  options: { signal?: AbortSignal; intervalMs?: number; timeoutMs?: number } = {},
): Promise<ActivityIngestionJob> {
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? POLL_TIMEOUT_MS
  const deadline = Date.now() + timeoutMs

  for (;;) {
    const job = await fetchIngestionJob(jobId, { signal: options.signal })
    if (isTerminalIngestionJob(job)) {
      if (job.status === 'failed') {
        throw new IngestionJobFailedError(job.error_code)
      }
      return job
    }
    if (Date.now() >= deadline) {
      throw new IngestionJobTimeoutError()
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
}

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
 * Returns a copy of the feed cache with any row matching a given activity's id
 * swapped for that activity, leaving position and every other row untouched.
 * Pure and immutable — never mutates in place.
 *
 * @param data - The cached infinite-feed value, or `undefined` when unpopulated.
 * @param activities - The refreshed activities to swap in.
 * @returns The updated feed value, or `undefined` when there was nothing cached.
 */
export function replaceActivitiesInFeed(
  data: InfiniteData<Activity[]> | undefined,
  activities: Activity[],
): InfiniteData<Activity[]> | undefined {
  if (!data || activities.length === 0) {
    return data
  }
  const byId = new Map(activities.map((activity) => [activity.id, activity]))
  return {
    ...data,
    pages: data.pages.map((page) => page.map((activity) => byId.get(activity.id) ?? activity)),
  }
}

/**
 * Writes activities over their existing rows in the viewer's own home feed.
 *
 * @param queryClient - The query client holding the feed caches.
 * @param activities - The refreshed activities to swap in.
 * @returns Nothing.
 */
function patchUserFeed(queryClient: QueryClient, activities: Activity[]): void {
  queryClient.setQueriesData<InfiniteData<Activity[]>>(
    {
      queryKey: queryKeys.activities.lists(),
      predicate: (query) => activityListScope(query.queryKey) === 'user-feed',
    },
    (data) => replaceActivitiesInFeed(data, activities),
  )
}

/**
 * Re-fetches activities that arrived without a map thumbnail and patches the
 * feed as each one lands, so a fresh upload gains its map without a reload.
 *
 * Each id is registered as awaiting (so its card can show a placeholder) and
 * cleared the moment it resolves — or when the retries run out.
 *
 * Gives up silently after {@link THUMBNAIL_RETRY_DELAYS_MS}: an activity with no
 * GPS track never gets a thumbnail, and a genuinely delayed one is picked up by
 * the server's periodic backfill and the next feed refetch.
 *
 * @param queryClient - The query client holding the feed caches.
 * @param activityIds - Ids of the activities still missing a thumbnail.
 * @returns A promise resolving once every id resolved or the retries ran out.
 */
async function backfillMissingThumbnails(
  queryClient: QueryClient,
  activityIds: number[],
): Promise<void> {
  let awaiting = activityIds
  markAwaitingThumbnail(awaiting)
  try {
    for (const delayMs of THUMBNAIL_RETRY_DELAYS_MS) {
      await new Promise((resolve) => setTimeout(resolve, delayMs))
      const refreshed = (
        await Promise.all(
          awaiting.map((id) => fetchActivity(id, { authenticated: true }).catch(() => null)),
        )
      ).filter((activity): activity is Activity => activity !== null)

      const ready = refreshed.filter((activity) => activity.mapThumbnailPath !== null)
      if (ready.length > 0) {
        patchUserFeed(queryClient, ready)
        const readyIds = ready.map((activity) => activity.id)
        clearAwaitingThumbnail(readyIds)
        const resolved = new Set(readyIds)
        awaiting = awaiting.filter((id) => !resolved.has(id))
      }
      if (awaiting.length === 0) {
        return
      }
    }
  } finally {
    // Whatever is left never arrived in time; drop the placeholder rather than
    // leaving a card pulsing forever.
    clearAwaitingThumbnail(awaiting)
  }
}

/**
 * Write-path reference for file uploads: a TanStack mutation that uploads one
 * activity file, waits for the background import, and reconciles the activities
 * cache.
 *
 * The upload request returns a `202` job handle rather than the parsed
 * activities \u2014 parsing is seconds of CPU and now runs on a background worker \u2014
 * so the mutation polls that job to completion before resolving. The mutation
 * therefore stays pending (and the feed's upload placeholder stays up) for the
 * whole import, exactly as it did when the request was synchronous.
 *
 * The completed job carries the ids it created, which are fetched and
 * optimistically pinned to the top of the viewer's home feed (see
 * {@link prependActivitiesToFeed}) so a fresh upload is immediately visible
 * instead of buried in its chronological position. Its map thumbnail is
 * rendered by a separate background job, so any activity that arrives without
 * one is chased briefly and patched in place (see
 * {@link backfillMissingThumbnails}).
 *
 * The home feeds are deliberately excluded from the settle-time invalidation \u2014
 * refetching them would reorder the new activity out of view before the viewer
 * notices it; a full reload restores the server-authoritative ordering. Every
 * other activities query (stats, counts, summaries, list views) still refetches
 * so those stay authoritative.
 *
 * @returns The TanStack mutation. Call `mutate(file)` / `mutateAsync(file)`.
 */
export function useUploadActivityFileMutation() {
  const queryClient = useQueryClient()

  return useMutation<ActivityIngestionJob, Error, File>({
    mutationFn: async (file) => {
      // One key per logical upload, so any replay of this same request — the
      // 401-refresh retry inside apiFetch today, a mutation retry later — is
      // answered with the original job instead of importing the file twice.
      const job = await uploadActivityFile(file, { idempotencyKey: crypto.randomUUID() })
      return pollIngestionJob(job.id)
    },
    onSuccess: async (job) => {
      // The job reports what it created, so fetch exactly those rows rather
      // than refetching the whole feed. A failed fetch drops that one row from
      // the optimistic pin; the settle-time invalidation still corrects it.
      const created = (
        await Promise.all(
          job.activity_ids.map((id) =>
            fetchActivity(id, { authenticated: true }).catch(() => null),
          ),
        )
      ).filter((activity): activity is Activity => activity !== null)
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

      // Thumbnail rendering reacts to `activity.created` on a background worker,
      // so it can finish after the upload job the poll above waited on. Chase
      // the ones that came back without a map rather than pinning a mapless
      // card until the next full reload. Deliberately not awaited: the upload is
      // already done, and the mutation must resolve so the UI placeholder clears.
      const awaitingThumbnail = created
        .filter((activity) => activity.mapThumbnailPath === null)
        .map((activity) => activity.id)
      if (awaitingThumbnail.length > 0) {
        void backfillMissingThumbnails(queryClient, awaitingThumbnail)
      }
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
