import { computed, watch } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'

import type { ProfileExportStatus, ProfileImportStatus } from '@/features/profile/types'
import type { StepUpInput } from '@/features/security/types'

import { invalidateActivityData } from '@/composables/useInvalidatingMutation'
import { useJobQuery, useLatestJobQuery } from '@/composables/useJobQuery'
import { isTerminalJobState, refreshLatestJobOnConflict, seedJob } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'
import {
  downloadProfileExport,
  importProfileData,
  requestProfileExport,
} from '@/features/profile/services/dataTransfer'

const POLL_MS = 3000

/**
 * Finds a profile job of one kind and follows it to a terminal state. The latest job of the kind is
 * looked up, so a job started earlier (another tab, a page reload) shows too; a job a 202 just
 * returned is seeded into both caches and followed from the start.
 *
 * @param kind - The job kind to find.
 * @returns The job's current state, or `null` when the user has none.
 */
function useProfileJob<K extends 'profile_export' | 'profile_import'>(kind: K) {
  const latest = useLatestJobQuery(kind)
  const jobId = computed(() => latest.data.value?.id ?? null)
  const followed = useJobQuery<K>(jobId, { intervalMs: POLL_MS })
  return computed(() => followed.data.value ?? latest.data.value ?? null)
}

/**
 * Export mutation, run after step-up. It only queues the export; the outcome comes from
 * {@link useProfileExportQuery}, which this seeds with the queued job so polling starts
 * straight away.
 *
 * @returns The TanStack Query mutation for requesting a profile export.
 */
export function useExportProfileMutation() {
  const client = useQueryClient()

  return useMutation<ProfileExportStatus, Error, StepUpInput>({
    mutationFn: (input) => requestProfileExport(input),
    onSuccess: (job) => seedJob(client, job),
    onError: (error) => refreshLatestJobOnConflict(client, 'profile_export', error),
  })
}

/**
 * Follows the user's profile export until it reaches a terminal state. It also
 * picks up an export that was started earlier (another tab, a page reload).
 *
 * @returns The export job's current state, or `null` when the user has none.
 */
export function useProfileExportQuery() {
  return useProfileJob('profile_export')
}

/**
 * Download mutation. Resolves with the finished export archive; the caller is
 * responsible for saving it (e.g. via `downloadBlob`). Modelled as a mutation
 * purely for the in-flight / error state — it changes no server state.
 *
 * @returns The TanStack Query mutation that produces the export blob.
 */
export function useDownloadProfileExportMutation() {
  return useMutation<Blob, Error, void>({
    mutationFn: () => downloadProfileExport(),
  })
}

/**
 * Refreshes every domain an import can change: profile, activities, gear,
 * notifications and the current-user shell. The import's own state is left alone,
 * so refreshing the profile cannot restart the polling that triggered it.
 *
 * @param client - The active query client.
 */
function invalidateImportedData(client: ReturnType<typeof useQueryClient>): void {
  void client.invalidateQueries({ queryKey: queryKeys.profile.detail() })
  void client.invalidateQueries({ queryKey: queryKeys.profile.defaultGear() })
  void client.invalidateQueries({ queryKey: queryKeys.gears.all() })
  void invalidateActivityData(client)
  void client.invalidateQueries({ queryKey: queryKeys.notifications.all() })
  void client.invalidateQueries({ queryKey: queryKeys.currentUser() })
}

/**
 * Import mutation. It only queues the import; the outcome comes from
 * {@link useProfileImportQuery}, which this seeds with the queued job so
 * polling starts straight away.
 *
 * @returns The TanStack Query mutation for importing a profile archive.
 */
export function useImportProfileMutation() {
  const client = useQueryClient()

  return useMutation<ProfileImportStatus, Error, File>({
    mutationFn: (file) => importProfileData(file),
    onSuccess: (job) => seedJob(client, job),
    onError: (error) => refreshLatestJobOnConflict(client, 'profile_import', error),
  })
}

/**
 * Follows the user's profile import until it reaches a terminal state. It also
 * picks up an import that was started earlier (another tab, a page reload).
 * Once the import finishes, the data it changed is refetched.
 *
 * @returns The import job's current state, or `null` when the user has none.
 */
export function useProfileImportQuery() {
  const client = useQueryClient()
  const job = useProfileJob('profile_import')

  // Refetch what the import changed once, when it goes from running to finished.
  watch(job, (next, previous) => {
    if (
      previous &&
      !isTerminalJobState(previous.status) &&
      next &&
      isTerminalJobState(next.status)
    ) {
      invalidateImportedData(client)
    }
  })

  return job
}
