import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { Activity, ActivityStats } from '@/features/activities/types'
import type { GoalProgress } from '@/features/goals/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  type ActivityStatsTimeframe,
  fetchActivityStats,
  fetchFollowersActivities,
  fetchUserActivities,
  fetchUserThisMonthActivityCount,
  fetchUserWeekActivities,
  refreshActivities,
} from '@/features/activities/services/activities'
import { fetchGoalResults } from '@/features/goals/services/goals'

/** Default number of activities fetched per feed page (matches v1's fallback). */
export const DEFAULT_FEED_PAGE_SIZE = 25

/** Resolves a reactive user id to a positive number, or `0` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<number | null>): number {
  const value = toValue(userId)
  return value !== null && Number.isFinite(value) && value > 0 ? value : 0
}

/**
 * The home dashboard's infinite feed of the viewer's own activities. Follows the
 * canonical infinite-query pattern (see `useInfiniteNotificationsQuery`): keyed
 * on page size only so every page shares one cache entry, and gated on a valid
 * user id and authentication so it never fires for a logged-out viewer.
 *
 * @param userId - Reactive id of the feed owner (the authenticated viewer).
 * @param pageSize - Records per page.
 * @param enabled - Reactive gate (e.g. "this feed tab is active") ANDed with the
 *   auth/id gate so an unselected feed never fetches.
 * @returns The TanStack infinite-query result for the user's activity feed.
 */
export function useUserActivitiesFeed(
  userId: MaybeRefOrGetter<number | null>,
  pageSize: number = DEFAULT_FEED_PAGE_SIZE,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.activities.userFeed(id.value, pageSize)),
    queryFn: ({ pageParam, signal }) => fetchUserActivities(id.value, pageParam, pageSize, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage: Activity[], _allPages, lastPageParam: number) =>
      lastPage.length < pageSize ? undefined : lastPageParam + 1,
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value > 0),
  })
}

/**
 * A user's activities for a configured calendar week, backing the public profile's
 * week-by-week activity browser (v1 parity). Week `0` is the current week and
 * each increment steps one week into the past. Gated on a valid user id,
 * authentication, and the supplied `enabled` flag (e.g. "the Activities tab is
 * active") so it never fetches for an unselected tab.
 *
 * @param userId - Reactive id of the profile owner.
 * @param week - Reactive week offset (0 = this week).
 * @param enabled - Reactive gate ANDed with the auth/id gate.
 * @returns The TanStack query result for that week's activities.
 */
export function useUserWeekActivitiesQuery(
  userId: MaybeRefOrGetter<number | null>,
  week: MaybeRefOrGetter<number>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))
  const weekValue = computed(() => toValue(week))

  return useQuery<Activity[]>({
    queryKey: computed(() => queryKeys.activities.weekActivities(id.value, weekValue.value)),
    queryFn: ({ signal }) => fetchUserWeekActivities(id.value, weekValue.value, signal),
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * The home dashboard's infinite feed of activities from the people the viewer
 * follows. Same shape as {@link useUserActivitiesFeed}.
 *
 * @param userId - Reactive id of the viewer.
 * @param pageSize - Records per page.
 * @param enabled - Reactive gate (e.g. "this feed tab is active") ANDed with the
 *   auth/id gate so an unselected feed never fetches.
 * @returns The TanStack infinite-query result for the followed-users feed.
 */
export function useFollowersActivitiesFeed(
  userId: MaybeRefOrGetter<number | null>,
  pageSize: number = DEFAULT_FEED_PAGE_SIZE,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.activities.followersFeed(id.value, pageSize)),
    queryFn: ({ pageParam, signal }) =>
      fetchFollowersActivities(id.value, pageParam, pageSize, signal),
    initialPageParam: 1,
    getNextPageParam: (lastPage: Activity[], _allPages, lastPageParam: number) =>
      lastPage.length < pageSize ? undefined : lastPageParam + 1,
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value > 0),
  })
}

/**
 * A user's per-sport aggregated stats for the current week or month, backing the
 * home dashboard's distance/time/calories summary. Gated on a valid user id and
 * authentication.
 *
 * @param userId - Reactive id of the user whose stats to load.
 * @param timeframe - `week` (this week) or `month` (this month).
 * @returns The TanStack query result for the per-sport stats.
 */
export function useActivityStatsQuery(
  userId: MaybeRefOrGetter<number | null>,
  timeframe: ActivityStatsTimeframe,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<ActivityStats>({
    queryKey: computed(() => queryKeys.activities.stats(id.value, timeframe)),
    queryFn: ({ signal }) => fetchActivityStats(id.value, timeframe, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * A user's count of activities recorded this month, backing the public-profile
 * header's headline figure. Gated on a valid user id and authentication.
 *
 * @param userId - Reactive id of the user whose monthly count to load.
 * @returns The TanStack query result for the this-month activity count.
 */
export function useUserMonthlyActivityCountQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useQuery<number>({
    queryKey: computed(() => queryKeys.activities.monthCount(id.value)),
    queryFn: ({ signal }) => fetchUserThisMonthActivityCount(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * The viewer's per-goal progress for the current interval, backing the home
 * dashboard's goal-results panel (and the public profile's own-goals panel).
 * Always scoped to the authenticated viewer (the backend's `profile/goals`
 * endpoint), so callers should only enable it on the viewer's own profile.
 *
 * @param enabled - Reactive gate ANDed with the auth gate (e.g. "this is my
 *   own profile"); defaults to always-on for the home dashboard.
 * @returns The TanStack query result for the goal progress list.
 */
export function useGoalResultsQuery(enabled: MaybeRefOrGetter<boolean> = true) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<GoalProgress[]>({
    queryKey: queryKeys.goals.results(),
    queryFn: ({ signal }) => fetchGoalResults(signal),
    enabled: computed(() => toValue(enabled) && isAuthenticated.value),
    staleTime: 5 * 60_000,
  })
}

/**
 * Triggers a refresh of the viewer's linked-integration activities (Strava /
 * Garmin Connect). On settle it invalidates the activities domain so every feed
 * refetches and shows any newly imported activities.
 *
 * @returns The TanStack mutation for refreshing integration activities.
 */
export function useRefreshActivitiesMutation() {
  const client = useQueryClient()

  return useMutation<Activity[], Error, void>({
    mutationFn: () => refreshActivities(),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.activities.all() })
    },
  })
}
