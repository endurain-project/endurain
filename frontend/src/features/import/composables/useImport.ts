import { computed, ref, watch, type Ref } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { invalidateActivityData } from '@/composables/useInvalidatingMutation'
import { useJobQuery, useLatestJobQuery } from '@/composables/useJobQuery'
import { isTerminalJobState, refreshLatestJobOnConflict, seedJob } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'
import {
  type BulkImportSource,
  bulkImportFromArchive,
  bulkImportFromFolder,
  importStravaGear,
} from '@/features/import/services/import'
import type { ActivityIngestionJob } from '@/features/upload/types'

/** How long to wait between progress polls of a running import. */
const PROGRESS_POLL_MS = 3000

/** Starts a bulk import of the files in the user's folder on the server. */
export function useBulkImportFromFolderMutation() {
  const client = useQueryClient()
  return useMutation<ActivityIngestionJob, Error, BulkImportSource>({
    mutationFn: (source) => bulkImportFromFolder(source),
    onSuccess: (job) => seedJob(client, job),
    onError: (error) => refreshLatestJobOnConflict(client, 'activity_bulk_import', error),
  })
}

/** Uploads a ZIP archive for bulk import. */
export function useBulkImportFromArchiveMutation() {
  const client = useQueryClient()
  return useMutation<ActivityIngestionJob, Error, { file: File; source: BulkImportSource }>({
    // One key per submit, so a replay of this same request (the 401-refresh retry inside apiFetch)
    // is answered with the original import instead of starting another.
    mutationFn: ({ file, source }) =>
      bulkImportFromArchive(file, source, { idempotencyKey: crypto.randomUUID() }),
    onSuccess: (job) => seedJob(client, job),
    onError: (error) => refreshLatestJobOnConflict(client, 'activity_bulk_import', error),
  })
}

/**
 * Follows one bulk import until it reaches a terminal state.
 *
 * A bulk import is worked through in batches over minutes or hours, so unlike a
 * single upload it is followed by a query that stops on its own, and the caller
 * keeps only the job id. A finished import has created activities, so the
 * activity queries are refreshed once it ends.
 *
 * @param jobId - The accepted import's job id, or `null` when none is running.
 * @returns The query; `data` is the job's current progress.
 */
export function useBulkImportJobQuery(jobId: Ref<string | null>) {
  const client = useQueryClient()
  const query = useJobQuery<'activity_bulk_import'>(jobId, { intervalMs: PROGRESS_POLL_MS })
  watch(
    () => query.data.value?.status,
    (status) => {
      if (status !== undefined && isTerminalJobState(status)) {
        void invalidateActivityData(client)
      }
    },
  )
  return query
}

/**
 * Finds the user's latest bulk import of one source and follows it to a terminal state, so an
 * import started earlier (a page reload, another tab) shows again while it runs. An import that
 * was already finished when first read is not shown; one seen running, started here or named by
 * a 409 stays visible after it ends, so the user sees the outcome. An import of the other source
 * is ignored.
 *
 * @param source - The archive layout this screen imports.
 * @returns The import job's current state, or `null` when there is none to show.
 */
export function useBulkImportJob(source: BulkImportSource) {
  const latest = useLatestJobQuery('activity_bulk_import')
  const mine = computed(() => {
    const job = latest.data.value
    return job && job.import_source === source ? job : null
  })
  const jobId = computed(() => mine.value?.id ?? null)
  const followed = useBulkImportJobQuery(jobId)
  const current = computed(() => followed.data.value ?? mine.value)

  const seenActiveId = ref<string | null>(null)
  watch(
    current,
    (job) => {
      if (job && !isTerminalJobState(job.status)) {
        seenActiveId.value = job.id
      }
    },
    { immediate: true },
  )

  return computed(() => {
    const job = current.value
    return job && (!isTerminalJobState(job.status) || seenActiveId.value === job.id) ? job : null
  })
}

/** Imports Strava bikes from an uploaded CSV; refreshes gear lists on success. */
export function useImportStravaBikesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, File>({
    mutationFn: (file) => importStravaGear(file, 'bike'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}

/** Imports Strava shoes from an uploaded CSV; refreshes gear lists on success. */
export function useImportStravaShoesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, File>({
    mutationFn: (file) => importStravaGear(file, 'shoes'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}
