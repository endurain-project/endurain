import { type InfiniteData, useMutation, useQueryClient } from '@tanstack/vue-query'

import { fetchActivity } from '@/features/activities/services/activities'
import type { Activity } from '@/features/activities/types'
import { fetchUploadJob, uploadActivityFile } from '@/features/upload/services/upload'
import { type ActivityUploadJob, isTerminalUploadJob } from '@/features/upload/types'
import { queryKeys } from '@/services/queryKeys'

/** How long to wait between upload-job status polls. */
const POLL_INTERVAL_MS = 1500

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
export class UploadJobFailedError extends Error {
  /**
   * @param code - The server's sanitized failure reason, when it gave one.
   */
  constructor(readonly code: string | null | undefined) {
    super(`Activity import failed: ${code ?? 'unknown'}`)
    this.name = 'UploadJobFailedError'
  }
}

/**
 * Raised when an upload job is still running after {@link POLL_TIMEOUT_MS}.
 * The import may still succeed server-side; only the client stopped watching.
 */
export class UploadJobTimeoutError extends Error {
  constructor() {
    super('Timed out waiting for the activity import to finish.')
    this.name = 'UploadJobTimeoutError'
  }
}

/**
 * Waits for a queued import to reach a terminal state.
 *
 * @param jobId - The job returned by the upload request.
 * @param options - Optional abort signal, polling interval, and timeout.
 * @returns The completed job.
 * @throws {UploadJobFailedError} When the import finished unsuccessfully.
 * @throws {UploadJobTimeoutError} When it is still running at the deadline.
 */
export async function pollUploadJob(
  jobId: string,
  options: { signal?: AbortSignal; intervalMs?: number; timeoutMs?: number } = {},
): Promise<ActivityUploadJob> {
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS
  const timeoutMs = options.timeoutMs ?? POLL_TIMEOUT_MS
  const deadline = Date.now() + timeoutMs

  for (;;) {
    const job = await fetchUploadJob(jobId, { signal: options.signal })
    if (isTerminalUploadJob(job)) {
      if (job.status === 'failed') {
        throw new UploadJobFailedError(job.error_code)
      }
      return job
    }
    if (Date.now() >= deadline) {
      throw new UploadJobTimeoutError()
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
 * {@link prependActivitiesToFeed}) so a fresh upload is immediately visible \u2014
 * with its map \u2014 instead of buried in its chronological position.
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

  return useMutation<ActivityUploadJob, Error, File>({
    mutationFn: async (file) => {
      const job = await uploadActivityFile(file)
      return pollUploadJob(job.id)
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
