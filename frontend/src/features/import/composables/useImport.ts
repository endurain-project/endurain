import { useMutation, useQueryClient } from '@tanstack/vue-query'

import { queryKeys } from '@/services/queryKeys'
import {
  bulkImportActivities,
  importStravaActivities,
  importStravaBikes,
  importStravaShoes,
} from '@/features/import/services/import'
import type { ActivityIngestionJob } from '@/features/upload/types'

/** Bulk-imports activity files from the server's bulk-import folder (background). */
export function useBulkImportMutation() {
  return useMutation<ActivityIngestionJob[], Error, void>({
    mutationFn: () => bulkImportActivities(),
  })
}

/** Queues activities from a Strava bulk export for import (background). */
export function useImportStravaActivitiesMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => importStravaActivities() })
}

/** Imports Strava bikes (synchronous); refreshes gear lists on success. */
export function useImportStravaBikesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: () => importStravaBikes(),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}

/** Imports Strava shoes (synchronous); refreshes gear lists on success. */
export function useImportStravaShoesMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: () => importStravaShoes(),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
    },
  })
}
