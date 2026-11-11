import { watch, type Ref } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { invalidateActivityData } from '@/composables/useInvalidatingMutation'
import { useJobQuery } from '@/composables/useJobQuery'
import { isTerminalJobState, seedJob } from '@/services/jobStatus'
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
  })
}

/** Uploads a ZIP archive for bulk import. */
export function useBulkImportFromArchiveMutation() {
  const client = useQueryClient()
  return useMutation<ActivityIngestionJob, Error, { file: File; source: BulkImportSource }>({
    mutationFn: ({ file, source }) => bulkImportFromArchive(file, source),
    onSuccess: (job) => seedJob(client, job),
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
