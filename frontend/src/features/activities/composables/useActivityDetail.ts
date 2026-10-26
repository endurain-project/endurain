import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  Activity,
  ActivityEditInput,
  ActivityMedia,
  ActivityOwner,
} from '@/features/activities/types'
import type { Gear } from '@/features/gears/types'
import type { Units } from '@/features/activities/utils/format'

import { ACTIVITY_ROW_INDEPENDENT_KEYS, queryKeys } from '@/services/queryKeys'
import { invalidateExcept } from '@/composables/useInvalidatingMutation'
import { useCurrentUser } from '@/features/auth/composables/useCurrentUser'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'
import { useAuthStore } from '@/features/auth/stores/auth'
import { fetchGearsByType } from '@/features/gears/services/gears'
import { fetchActivityOwner } from '@/features/activities/services/activityOwner'
import {
  deleteActivity,
  editActivity,
  fetchActivityDetail,
  fetchActivityExerciseTitles,
  fetchActivityLaps,
  fetchActivitySets,
  fetchActivityStreams,
  fetchActivityWorkoutSteps,
  setActivityGear,
} from '@/features/activities/services/activities'
import {
  deleteActivityMedia,
  fetchActivityMedia,
  uploadActivityMedia,
} from '@/features/activities/services/activityMedia'

/** Resolves a reactive activity id to a positive number, or `0` when invalid. */
function resolveId(id: MaybeRefOrGetter<number | null>): number {
  const value = toValue(id)
  return value !== null && Number.isFinite(value) && value > 0 ? value : 0
}

/**
 * Loads a single activity. Reads the authenticated endpoint when logged in and
 * the public shareable-link endpoint otherwise, so the same route serves owners
 * and public viewers. Gated on a valid id.
 *
 * The response also carries the activity's laps, sets and workout steps, which are seeded into the
 * caches of their own queries, so those make no request. A collection that did not arrive in full
 * is left to its own query, which reads every page.
 *
 * @param id - Reactive activity id from the route.
 * @returns The TanStack query result; data is `null` when not found/accessible.
 */
export function useActivityQuery(id: MaybeRefOrGetter<number | null>) {
  const client = useQueryClient()
  const auth = useAuthStore()

  return useQuery({
    queryKey: computed(() => queryKeys.activities.detail(resolveId(id))),
    queryFn: async ({ signal }) => {
      const activityId = resolveId(id)
      const detail = await fetchActivityDetail(activityId, {
        authenticated: auth.isAuthenticated,
        signal,
      })
      if (!detail) {
        return null
      }
      if (detail.laps) {
        client.setQueryData(queryKeys.activities.laps(activityId), detail.laps)
      }
      if (detail.sets) {
        client.setQueryData(queryKeys.activities.sets(activityId), detail.sets)
      }
      if (detail.workoutSteps) {
        client.setQueryData(queryKeys.activities.workoutSteps(activityId), detail.workoutSteps)
      }
      return detail.activity
    },
    enabled: computed(() => resolveId(id) > 0),
  })
}

/**
 * Loads the activity owner's public-facing identity (name + avatar). The owner
 * viewing their own activity is resolved from the cached current user, so this
 * only fetches for other viewers — authenticated viewers via the authed user
 * endpoint, anonymous viewers via the public one (which the backend gates on the
 * "show user info on public links" setting, returning `null` when disabled).
 *
 * @param activity - Reactive activity supplying the owner's user id.
 * @returns The TanStack query result; data is `null` when the owner is hidden.
 */
export function useActivityOwnerQuery(activity: MaybeRefOrGetter<Activity | null | undefined>) {
  const auth = useAuthStore()
  const { data: currentUser } = useCurrentUser()
  const ownerId = computed(() => toValue(activity)?.userId ?? null)

  return useQuery<ActivityOwner | null>({
    queryKey: computed(() => queryKeys.activities.owner(ownerId.value ?? 0)),
    queryFn: ({ signal }) =>
      fetchActivityOwner(ownerId.value as number, auth.isAuthenticated, signal),
    enabled: computed(() => ownerId.value !== null && currentUser.value?.id !== ownerId.value),
    staleTime: 5 * 60_000,
  })
}

/**
 * Loads an activity's metric streams. Gated on a valid id and an explicit
 * `enabled` flag so the view only fetches once the activity itself has loaded
 * (avoiding doomed requests when a public activity is not shareable).
 *
 * @param id - Reactive activity id.
 * @param enabled - Reactive gate (typically "activity loaded").
 * @returns The TanStack query result for the streams.
 */
export function useActivityStreamsQuery(
  id: MaybeRefOrGetter<number | null>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const auth = useAuthStore()

  return useQuery({
    queryKey: computed(() => queryKeys.activities.streams(resolveId(id))),
    queryFn: ({ signal }) =>
      fetchActivityStreams(resolveId(id), { authenticated: auth.isAuthenticated, signal }),
    enabled: computed(() => resolveId(id) > 0 && toValue(enabled)),
    staleTime: 5 * 60_000,
  })
}

/**
 * Loads an activity's laps. Gated like {@link useActivityStreamsQuery}.
 *
 * @param id - Reactive activity id.
 * @param enabled - Reactive gate (typically "activity loaded").
 * @returns The TanStack query result for the laps.
 */
export function useActivityLapsQuery(
  id: MaybeRefOrGetter<number | null>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const auth = useAuthStore()

  return useQuery({
    queryKey: computed(() => queryKeys.activities.laps(resolveId(id))),
    queryFn: ({ signal }) =>
      fetchActivityLaps(resolveId(id), { authenticated: auth.isAuthenticated, signal }),
    enabled: computed(() => resolveId(id) > 0 && toValue(enabled)),
    staleTime: 5 * 60_000,
  })
}

/**
 * Loads an activity's planned workout steps. Gated like
 * {@link useActivityStreamsQuery}; the view only enables it for activity types
 * that carry workout data (strength sessions, swims).
 *
 * @param id - Reactive activity id.
 * @param enabled - Reactive gate ("activity loaded" + workout-capable type).
 * @returns The TanStack query result for the workout steps.
 */
export function useActivityWorkoutStepsQuery(
  id: MaybeRefOrGetter<number | null>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const auth = useAuthStore()

  return useQuery({
    queryKey: computed(() => queryKeys.activities.workoutSteps(resolveId(id))),
    queryFn: ({ signal }) =>
      fetchActivityWorkoutSteps(resolveId(id), { authenticated: auth.isAuthenticated, signal }),
    enabled: computed(() => resolveId(id) > 0 && toValue(enabled)),
    staleTime: 5 * 60_000,
  })
}

/**
 * Loads an activity's performed workout sets. Gated like
 * {@link useActivityWorkoutStepsQuery}.
 *
 * @param id - Reactive activity id.
 * @param enabled - Reactive gate ("activity loaded" + workout-capable type).
 * @returns The TanStack query result for the workout sets.
 */
export function useActivitySetsQuery(
  id: MaybeRefOrGetter<number | null>,
  enabled: MaybeRefOrGetter<boolean>,
) {
  const auth = useAuthStore()

  return useQuery({
    queryKey: computed(() => queryKeys.activities.sets(resolveId(id))),
    queryFn: ({ signal }) =>
      fetchActivitySets(resolveId(id), { authenticated: auth.isAuthenticated, signal }),
    enabled: computed(() => resolveId(id) > 0 && toValue(enabled)),
    staleTime: 5 * 60_000,
  })
}

/**
 * Loads the exercise-name catalogue used to resolve workout step/set exercise
 * names. The catalogue is static, so it is cached indefinitely and shared
 * across activities. Gated so it only loads when a workout table will render.
 *
 * @param enabled - Reactive gate ("activity loaded" + workout-capable type).
 * @returns The TanStack query result for the exercise titles.
 */
export function useActivityExerciseTitlesQuery(enabled: MaybeRefOrGetter<boolean>) {
  const auth = useAuthStore()

  return useQuery({
    queryKey: queryKeys.activities.exerciseTitles(),
    queryFn: ({ signal }) =>
      fetchActivityExerciseTitles({ authenticated: auth.isAuthenticated, signal }),
    enabled: computed(() => toValue(enabled)),
    staleTime: Infinity,
  })
}

/**
 * The gears that can be associated with an activity of the given gear type, for
 * the activity gear picker. Gated on authentication and a valid (non-`null`)
 * gear type so non-gear activities never fetch.
 *
 * @param gearType - Reactive numeric gear type, or `null` when the activity
 *   family has no associated gear.
 * @returns The TanStack query result for the matching gears.
 */
export function useActivityGearOptionsQuery(gearType: MaybeRefOrGetter<number | null>) {
  const auth = useAuthStore()
  const type = computed(() => toValue(gearType))

  return useQuery<Gear[]>({
    queryKey: computed(() => queryKeys.gears.byType(type.value ?? 0)),
    queryFn: ({ signal }) => fetchGearsByType(type.value as number, signal),
    enabled: computed(() => auth.isAuthenticated && (type.value ?? 0) > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * Marks everything derived from activity rows stale: the lists and feeds, the
 * summaries and stats, the name search and the type filters.
 *
 * @param client - The active query client.
 */
function invalidateActivityAggregates(client: QueryClient): void {
  void invalidateExcept(client, queryKeys.activities.all(), ACTIVITY_ROW_INDEPENDENT_KEYS)
}

/**
 * Marks every gear's totals and activity rows stale, since they depend on which
 * activities carry the gear. Stale rather than refetched: the gear card on the
 * activity page switches to the new gear (or goes away) on its own, and anything
 * that shows the old gear later refetches on mount.
 *
 * @param client - The active query client.
 */
function invalidateGearUsage(client: QueryClient): void {
  const refetchType = 'none'
  void client.invalidateQueries({ queryKey: queryKeys.gears.details(), refetchType })
  void client.invalidateQueries({ queryKey: queryKeys.gears.activitiesLists(), refetchType })
}

/**
 * Refetches one activity's detail only, so a save refused as stale (412) replaces
 * the copy the user was editing with the current one.
 *
 * @param client - The active query client.
 * @param id - The activity whose cached copy can no longer be trusted.
 */
function refetchActivity(client: QueryClient, id: number): void {
  void client.invalidateQueries({ queryKey: queryKeys.activities.detail(id), exact: true })
}

/**
 * Sets (or clears, with `gearId: null`) the gear associated with an activity.
 * On success it writes the returned activity straight into the detail cache;
 * on settle it marks the activity-derived data and the gear totals stale. The
 * activity's sub-resources are left alone, and a failed save refetches only the
 * activity itself.
 *
 * @returns The TanStack mutation for updating an activity's gear.
 */
export function useSetActivityGearMutation() {
  const client = useQueryClient()

  return useMutation<Activity, Error, { activity: Activity; gearId: number | null }>({
    mutationFn: ({ activity, gearId }) => setActivityGear(activity, gearId),
    onSuccess: (updated) => {
      client.setQueryData(queryKeys.activities.detail(updated.id), updated)
    },
    onError: (_error, { activity }) => refetchActivity(client, activity.id),
    onSettled: () => {
      invalidateActivityAggregates(client)
      invalidateGearUsage(client)
    },
  })
}

/**
 * The unit system to present an activity in: the authenticated user's
 * preference, or the instance default (public server settings) for anonymous
 * public viewers. Mirrors v1's auth-vs-public unit resolution. Shares the
 * `public.serverSettings` query key so it reuses any warm cache.
 *
 * @returns A reactive unit system.
 */
export function useDisplayUnits(): ComputedRef<Units> {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const { data: currentUser } = useCurrentUser()

  const publicSettings = useQuery({
    queryKey: queryKeys.public.serverSettings(),
    queryFn: fetchPublicServerSettings,
    placeholderData: DEFAULT_PUBLIC_SERVER_SETTINGS,
    retry: 1,
    staleTime: 5 * 60_000,
    // Only public viewers need the instance default; authenticated viewers read
    // their own preference.
    enabled: computed(() => !isAuthenticated.value),
  })

  return computed<Units>(() => {
    if (isAuthenticated.value) {
      return currentUser.value?.units ?? 'metric'
    }
    return publicSettings.data.value?.units ?? 'metric'
  })
}

/**
 * Deletes an activity. On success it drops the activity and its sub-resources
 * from the cache instead of refetching them (the detail view is still mounted
 * until the caller navigates away, and would otherwise request an activity that
 * no longer exists); on settle it marks the lists, aggregates and gear totals
 * stale so they drop the removed activity.
 *
 * @returns The TanStack mutation for deleting an activity.
 */
export function useDeleteActivityMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, number>({
    mutationFn: (id) => deleteActivity(id),
    onSuccess: (_data, id) => {
      client.removeQueries({ queryKey: queryKeys.activities.detail(id) })
    },
    onSettled: () => {
      invalidateActivityAggregates(client)
      invalidateGearUsage(client)
    },
  })
}

/**
 * The photos attached to an activity. Authenticated-only (there is no public
 * media endpoint), gated on a valid id.
 *
 * @param id - Reactive activity id.
 * @returns The TanStack query result for the activity's media.
 */
export function useActivityMediaQuery(id: MaybeRefOrGetter<number | null>) {
  const auth = useAuthStore()

  return useQuery<ActivityMedia[]>({
    queryKey: computed(() => queryKeys.activities.media(resolveId(id))),
    queryFn: ({ signal }) => fetchActivityMedia(resolveId(id), signal),
    enabled: computed(() => auth.isAuthenticated && resolveId(id) > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * Uploads an image to an activity. On settle it invalidates that activity's
 * media query so the gallery refetches and shows the new photo.
 *
 * @param id - Reactive activity id.
 * @returns The TanStack mutation for uploading activity media.
 */
export function useUploadActivityMediaMutation(id: MaybeRefOrGetter<number | null>) {
  const client = useQueryClient()

  return useMutation<ActivityMedia, Error, File>({
    mutationFn: (file) => uploadActivityMedia(resolveId(id), file),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.activities.media(resolveId(id)) })
    },
  })
}

/**
 * Deletes one photo from an activity. On settle it invalidates that activity's
 * media query so the gallery drops the removed photo.
 *
 * @param id - Reactive activity id (for cache invalidation).
 * @returns The TanStack mutation for deleting activity media.
 */
export function useDeleteActivityMediaMutation(id: MaybeRefOrGetter<number | null>) {
  const client = useQueryClient()

  return useMutation<void, Error, number>({
    // The delete route is nested under the activity, so the id the composable
    // already tracks for cache invalidation is now part of the request path.
    mutationFn: (mediaId) => deleteActivityMedia(resolveId(id) ?? 0, mediaId),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.activities.media(resolveId(id)) })
    },
  })
}

/**
 * Applies a full edit to an activity. On success it writes the updated activity
 * into the detail cache; on settle it marks the lists and aggregates stale so
 * they reflect the new name/type/visibility. The activity's sub-resources are
 * left alone, and a failed save (e.g. a stale version) refetches only the
 * activity itself.
 *
 * @returns The TanStack mutation for editing an activity.
 */
export function useEditActivityMutation() {
  const client = useQueryClient()

  return useMutation<Activity, Error, { id: number; input: ActivityEditInput; version: number }>({
    mutationFn: ({ id, input, version }) => editActivity(id, input, version),
    onSuccess: (updated) => {
      client.setQueryData(queryKeys.activities.detail(updated.id), updated)
    },
    onError: (_error, { id }) => refetchActivity(client, id),
    onSettled: () => invalidateActivityAggregates(client),
  })
}
