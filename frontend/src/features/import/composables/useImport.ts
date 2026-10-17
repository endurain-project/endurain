import { computed, type Ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import {
  type BulkImportSource,
  bulkImportFromArchive,
  bulkImportFromFolder,
  importStravaBikes,
  importStravaShoes,
} from '@/features/import/services/import'
import { fetchIngestionJob } from '@/features/upload/services/upload'
import { type ActivityIngestionJob, isTerminalIngestionJob } from '@/features/upload/types'

/** How long to wait between progress polls of a running import. */
const PROGRESS_POLL_MS = 3000

/** Starts a bulk import of the files in the user's folder on the server. */
export function useBulkImportFromFolderMutation() {
  return useMutation<ActivityIngestionJob, Error, BulkImportSource>({
    mutationFn: (source) => bulkImportFromFolder(source),
  })
}

/** Uploads a ZIP archive for bulk import. */
export function useBulkImportFromArchiveMutation() {
  return useMutation<ActivityIngestionJob, Error, { file: File; source: BulkImportSource }>({
    mutationFn: ({ file, source }) => bulkImportFromArchive(file, source),
  })
}

/**
 * Follows one bulk import until it reaches a terminal state.
 *
 * A bulk import is worked through in batches over minutes or hours, so unlike a
 * single upload it is polled by a query that stops on its own, and the caller
 * keeps only the job id.
 *
 * @param jobId - The accepted import's job id, or `null` when none is running.
 * @returns The query; `data` is the job's current progress.
 */
export function useBulkImportJobQuery(jobId: Ref<string | null>) {
  const client = useQueryClient()
  return useQuery<ActivityIngestionJob, Error>({
    queryKey: computed(() => queryKeys.bulkImport.job(jobId.value ?? '')),
    queryFn: ({ signal }) => fetchIngestionJob(jobId.value as string, { signal }),
    enabled: computed(() => jobId.value !== null),
    refetchInterval: (query) => {
      const job = query.state.data
      if (job && isTerminalIngestionJob(job)) {
        // A finished import has created activities; refresh what shows them.
        void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
        return false
      }
      return PROGRESS_POLL_MS
    },
  })
}

/** Imports Strava bikes from an uploaded CSV; refreshes gear lists on success. */
export function useImportStravaBikesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, File>({
    mutationFn: (file) => importStravaBikes(file),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}

/** Imports Strava shoes from an uploaded CSV; refreshes gear lists on success. */
export function useImportStravaShoesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, File>({
    mutationFn: (file) => importStravaShoes(file),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}
