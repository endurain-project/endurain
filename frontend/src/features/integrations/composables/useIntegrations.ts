import { watch, type Ref } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'

import type {
  ActivityRefreshJob,
  DateRange,
  GarminLinkStatus,
  GarminLoginInput,
  GarminSyncStatus,
  StravaSyncStatus,
} from '@/features/integrations/types'

import { useJobQuery } from '@/composables/useJobQuery'
import { useToasts } from '@/composables/useToasts'
import { followJob, JobTimeoutError, runningJobId, seedJob } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'
import {
  linkGarmin,
  retrieveGarminActivities,
  retrieveGarminGear,
  retrieveGarminHealth,
  submitGarminMfa,
  unlinkGarmin,
} from '@/features/integrations/services/garmin'
import {
  retrieveStravaActivities,
  retrieveStravaGear,
  unlinkStrava,
} from '@/features/integrations/services/strava'

/**
 * Returns a callback that invalidates the self-profile so the integration link
 * status (read from `useProfileQuery`) refreshes after a link/unlink.
 */
function useProfileInvalidation(): () => void {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
  }
}

/**
 * Reports how a queued retrieval from a provider ended. The data it brings in refreshes through
 * the realtime hints, so this only tells the user the outcome.
 *
 * @param provider - The provider's name, as shown to the user.
 * @returns `follow`: follows a job to its end and toasts success or failure; `resumeOnConflict`:
 *   when a start request failed because the same retrieval is already running, follows that job
 *   and returns `true`, otherwise returns `false` and leaves the failure to the caller.
 */
export function useRetrievalOutcome(provider: string) {
  const { t } = useI18n()
  const toasts = useToasts()

  async function follow(jobId: string): Promise<void> {
    try {
      const job = await followJob(jobId)
      if (job.status === 'succeeded') {
        toasts.success(t('settings.integrations.retrieveFinished', { provider }))
      } else {
        toasts.error(t('settings.integrations.retrieveFailed', { provider }))
      }
    } catch (error) {
      // Giving up on a job that keeps running says nothing about its outcome, so stay quiet.
      if (!(error instanceof JobTimeoutError)) {
        toasts.error(t('settings.integrations.retrieveFailed', { provider }))
      }
    }
  }

  function resumeOnConflict(error: Error): boolean {
    const jobId = runningJobId(error)
    if (jobId === null) {
      return false
    }
    toasts.info(t('settings.integrations.retrieveAlreadyRunning', { provider }))
    void follow(jobId)
    return true
  }

  return { follow, resumeOnConflict }
}

/** Imports Strava activities for a date window (background task on the server). */
export function useRetrieveStravaActivitiesMutation() {
  return useMutation<ActivityRefreshJob, Error, DateRange>({
    mutationFn: (range) => retrieveStravaActivities(range),
  })
}

/** Imports the user's Strava gear (background task on the server). */
export function useRetrieveStravaGearMutation() {
  return useMutation<StravaSyncStatus, Error, void>({ mutationFn: () => retrieveStravaGear() })
}

/** Disconnects Strava and refreshes the profile link status. */
export function useUnlinkStravaMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkStrava(),
    onSuccess: invalidateProfile,
  })
}

/** How often the Garmin Connect link job is read while it runs and no hint can arrive. */
const GARMIN_LINK_POLL_MS = 1_500

/**
 * Starts linking a Garmin Connect account. It resolves as soon as the background login is
 * accepted, with the link job, which it seeds into the cache; {@link useGarminLinkQuery} then
 * follows it to its outcome.
 */
export function useLinkGarminMutation() {
  const client = useQueryClient()
  return useMutation<GarminLinkStatus, Error, GarminLoginInput>({
    mutationFn: (input) => linkGarmin(input),
    onSuccess: (job) => seedJob(client, job),
  })
}

/**
 * Follows a Garmin Connect link job until it completes or fails. A succeeded link refreshes the
 * profile's link status.
 *
 * @param jobId - The link job's id from the 202, or `null` while none is followed.
 * @returns The TanStack Query result for the job.
 */
export function useGarminLinkQuery(jobId: Ref<string | null>) {
  const invalidateProfile = useProfileInvalidation()
  const query = useJobQuery<'garmin_link'>(jobId, { intervalMs: GARMIN_LINK_POLL_MS })
  watch(
    () => query.data.value?.status,
    (status) => {
      if (status === 'succeeded') {
        invalidateProfile()
      }
    },
  )
  return query
}

/** Submits a Garmin Connect MFA code, unblocking a pending link request. */
export function useSubmitGarminMfaMutation() {
  return useMutation<void, Error, string>({ mutationFn: (code) => submitGarminMfa(code) })
}

/** Imports Garmin Connect activities for a date window (background task). */
export function useRetrieveGarminActivitiesMutation() {
  return useMutation<ActivityRefreshJob, Error, DateRange>({
    mutationFn: (range) => retrieveGarminActivities(range),
  })
}

/** Imports the user's Garmin Connect gear (background task). */
export function useRetrieveGarminGearMutation() {
  return useMutation<GarminSyncStatus, Error, void>({ mutationFn: () => retrieveGarminGear() })
}

/** Imports Garmin Connect health data for a date window (background task). */
export function useRetrieveGarminHealthMutation() {
  return useMutation<GarminSyncStatus, Error, DateRange>({
    mutationFn: (range) => retrieveGarminHealth(range),
  })
}

/** Disconnects Garmin Connect and refreshes the profile link status. */
export function useUnlinkGarminMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkGarmin(),
    onSuccess: invalidateProfile,
  })
}
