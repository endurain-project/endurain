import type { Ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { DateRange, GarminLinkStatus, GarminLoginInput } from '@/features/integrations/types'

import { queryKeys } from '@/services/queryKeys'
import {
  fetchGarminLinkStatus,
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

/** How often the Garmin Connect link status is read while the attempt is running. */
const GARMIN_LINK_POLL_MS = 1_500

/**
 * Starts linking a Garmin Connect account. It resolves as soon as the background login is
 * accepted; {@link useGarminLinkStatusQuery} then follows it to its outcome.
 */
export function useLinkGarminMutation() {
  return useMutation<GarminLinkStatus, Error, GarminLoginInput>({
    mutationFn: (input) => linkGarmin(input),
  })
}

/**
 * Follows a Garmin Connect link attempt by polling its status until it completes or fails.
 * It keeps polling in a background tab, because the user may be reading an MFA code in
 * another app. A completed link refreshes the profile's link status.
 *
 * @param enabled - Whether an attempt is being followed.
 * @returns The TanStack Query result for the attempt's status.
 */
export function useGarminLinkStatusQuery(enabled: Ref<boolean>) {
  const invalidateProfile = useProfileInvalidation()
  return useQuery<GarminLinkStatus, Error>({
    queryKey: queryKeys.integrations.garminLinkStatus(),
    queryFn: async ({ signal }) => {
      const status = await fetchGarminLinkStatus(signal)
      if (status.status === 'completed') {
        invalidateProfile()
      }
      return status
    },
    enabled,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'completed' || status === 'failed' ? false : GARMIN_LINK_POLL_MS
    },
    refetchIntervalInBackground: true,
    // A fresh attempt must not start from the previous attempt's outcome.
    gcTime: 0,
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
