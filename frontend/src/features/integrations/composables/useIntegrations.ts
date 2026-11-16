import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { DateRange, GarminLoginInput } from '@/features/integrations/types'

import { queryKeys } from '@/services/queryKeys'
import { fetchCorosStatus, syncCoros, unlinkCoros } from '@/features/integrations/services/coros'
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

/** Imports Strava activities for a date window (background task on the server). */
export function useRetrieveStravaActivitiesMutation() {
  return useMutation<void, Error, DateRange>({
    mutationFn: (range) => retrieveStravaActivities(range),
  })
}

/** Imports the user's Strava gear (background task on the server). */
export function useRetrieveStravaGearMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => retrieveStravaGear() })
}

/** Disconnects Strava and refreshes the profile link status. */
export function useUnlinkStravaMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkStrava(),
    onSuccess: invalidateProfile,
  })
}

/**
 * Links a Garmin Connect account. The request may stay pending until an MFA
 * code is supplied (see {@link useSubmitGarminMfaMutation}); on success it
 * refreshes the profile link status.
 */
export function useLinkGarminMutation() {
  const invalidateProfile = useProfileInvalidation()
  return useMutation<void, Error, GarminLoginInput>({
    mutationFn: (input) => linkGarmin(input),
    onSuccess: invalidateProfile,
  })
}

/** Submits a Garmin Connect MFA code, unblocking a pending link request. */
export function useSubmitGarminMfaMutation() {
  return useMutation<void, Error, string>({ mutationFn: (code) => submitGarminMfa(code) })
}

/** Imports Garmin Connect activities for a date window (background task). */
export function useRetrieveGarminActivitiesMutation() {
  return useMutation<void, Error, DateRange>({
    mutationFn: (range) => retrieveGarminActivities(range),
  })
}

/** Imports the user's Garmin Connect gear (background task). */
export function useRetrieveGarminGearMutation() {
  return useMutation<void, Error, void>({ mutationFn: () => retrieveGarminGear() })
}

/** Imports Garmin Connect health data for a date window (background task). */
export function useRetrieveGarminHealthMutation() {
  return useMutation<void, Error, DateRange>({
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

/**
 * COROS connection and last-sync status. Polled while the card is shown so a
 * background sync started from another tab or the scheduler becomes visible.
 *
 * @param enabled - Whether the profile says COROS is connected.
 * @returns The TanStack Query result for the COROS status.
 */
export function useCorosStatusQuery(enabled: MaybeRefOrGetter<boolean>) {
  return useQuery({
    queryKey: queryKeys.integrations.corosStatus(),
    queryFn: ({ signal }) => fetchCorosStatus(signal),
    enabled: computed(() => toValue(enabled)),
    refetchInterval: 30_000,
  })
}

/** Queues a COROS sync for the given range (last seven days when omitted). */
export function useSyncCorosMutation() {
  const client = useQueryClient()
  return useMutation<void, Error, DateRange | undefined>({
    mutationFn: (range) => syncCoros(range),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.integrations.corosStatus() })
    },
  })
}

/** Disconnects COROS and refreshes both the profile and the status card. */
export function useUnlinkCorosMutation() {
  const invalidateProfile = useProfileInvalidation()
  const client = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: () => unlinkCoros(),
    onSuccess: invalidateProfile,
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.integrations.corosStatus() })
    },
  })
}
