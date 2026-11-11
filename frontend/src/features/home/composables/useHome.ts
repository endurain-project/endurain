import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import {
  type QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/vue-query'

import type { ActivitySummary, ActivityFeedSlice, ActivityStats } from '@/features/activities/types'
import type { Schemas } from '@/types'
import type { GoalProgress } from '@/features/goals/types'

import { invalidateActivityData } from '@/composables/useInvalidatingMutation'
import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  type ActivityStatsTimeframe,
  fetchActivityStats,
  fetchFollowersActivities,
  fetchUserWeekActivities,
  refreshActivities,
} from '@/features/activities/services/activities'
import { fetchGoalResults } from '@/features/goals/services/goals'
import {
  floatPinnedActivities,
  refreshPinnedActivities,
} from '@/features/upload/composables/usePinnedActivities'
import { followIngestionJob } from '@/features/upload/composables/useUpload'
import type { ActivityIngestionJob } from '@/features/upload/types'

/** Default number of activities fetched per feed page (matches v1's fallback). */
export const DEFAULT_FEED_PAGE_SIZE = 25

/** Resolves a reactive user id to a positive number, or `0` when unavailable. */
function resolveUserId(userId: MaybeRefOrGetter<number | null>): number {
  const value = toValue(userId)
  return value !== null && Number.isFinite(value) && value > 0 ? value : 0
}

/**
 * Seeds each activity's media query with the photos its list response embedded, so
 * a card's gallery makes no `/media` request of its own. An activity the viewer
 * does not own is seeded empty, which is what its media endpoint answers.
 *
 * @param client - The query client holding the media queries.
 * @param activities - The mapped activities of one list response.
 */
export function seedActivityMedia(client: QueryClient, activities: ActivitySummary[]): void {
  for (const activity of activities) {
    client.setQueryData(queryKeys.activities.media(activity.id), activity.media)
  }
}

/**
 * Seeds the caches the cards of one feed slice read: each activity's media and each owner's
 * public profile, both of which arrive with the slice.
 *
 * @param client - The query client holding the media and owner queries.
 * @param slice - One slice of an activity feed.
 */
function seedFeedSlice(client: QueryClient, slice: ActivityFeedSlice): void {
  seedActivityMedia(client, slice.items)
  for (const [ownerId, owner] of slice.owners) {
    client.setQueryData(queryKeys.activities.owner(ownerId), owner)
  }
}

/**
 * The home dashboard's infinite feed of the viewer's own activities, read from the cursor feed with
 * `scope=mine` like {@link useFollowersActivitiesFeed}. Keyed on page size only so every page shares
 * one cache entry, and gated on a valid user id and authentication so it never fires for a
 * logged-out viewer.
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
  const client = useQueryClient()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  const query = useInfiniteQuery({
    queryKey: computed(() => queryKeys.activities.userFeed(id.value, pageSize)),
    queryFn: async ({ pageParam, signal }) => {
      const slice = await fetchFollowersActivities(pageParam, pageSize, 'mine', signal)
      seedFeedSlice(client, slice)
      if (pageParam === null) {
        await refreshPinnedActivities()
      }
      return slice
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastSlice: ActivityFeedSlice) => lastSlice.nextCursor ?? undefined,
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value > 0),
  })

  // Activities uploaded this session stay on top through any refetch. Derived
  // here rather than with `select` so a refreshed pin shows even when the
  // refetch returned the same pages.
  const data = computed(() => floatPinnedActivities(query.data.value))
  return { ...query, data }
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
 * @param firstDayOfWeek - Reactive first weekday of the viewer's weeks.
 * @param enabled - Reactive gate ANDed with the auth/id gate.
 * @returns The TanStack query result for that week's activities.
 */
export function useUserWeekActivitiesQuery(
  userId: MaybeRefOrGetter<number | null>,
  week: MaybeRefOrGetter<number>,
  firstDayOfWeek: MaybeRefOrGetter<Schemas['WeekDay']>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const client = useQueryClient()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))
  const weekValue = computed(() => toValue(week))
  const firstDay = computed(() => toValue(firstDayOfWeek))

  return useQuery<ActivitySummary[]>({
    queryKey: computed(() =>
      queryKeys.activities.weekActivities(id.value, weekValue.value, firstDay.value),
    ),
    queryFn: async ({ signal }) => {
      const activities = await fetchUserWeekActivities(
        id.value,
        weekValue.value,
        firstDay.value,
        signal,
      )
      seedActivityMedia(client, activities)
      return activities
    },
    enabled: computed(() => toValue(enabled) && isAuthenticated.value && id.value > 0),
    staleTime: 5 * 60_000,
  })
}

/**
 * The home dashboard's infinite feed of activities from the people the viewer
 * follows. Same shape as {@link useUserActivitiesFeed}. The owners' profiles arrive
 * with each slice and are seeded into the activity-owner cache the cards read.
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
  const client = useQueryClient()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const id = computed(() => resolveUserId(userId))

  return useInfiniteQuery({
    queryKey: computed(() => queryKeys.activities.followersFeed(id.value, pageSize)),
    queryFn: async ({ pageParam, signal }) => {
      const slice = await fetchFollowersActivities(pageParam, pageSize, 'following', signal)
      seedFeedSlice(client, slice)
      return slice
    },
    // Keyset, not offset: the server hands back the position of the last row it
    // returned, so activities arriving mid-scroll cannot shift the window.
    initialPageParam: null as string | null,
    getNextPageParam: (lastSlice: ActivityFeedSlice) => lastSlice.nextCursor ?? undefined,
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
 * Garmin Connect).
 *
 * The request returns a `202` job handle rather than the imported activities —
 * a provider sync is a chain of third-party round-trips and now runs on a
 * background worker — so the mutation polls that job to completion before
 * resolving. It therefore stays pending for the whole sync, exactly as it did
 * when the request was synchronous.
 *
 * On settle it invalidates the activities domain so every feed refetches and
 * shows any newly imported activities.
 *
 * @returns The TanStack mutation for refreshing integration activities.
 */
export function useRefreshActivitiesMutation() {
  const client = useQueryClient()

  return useMutation<ActivityIngestionJob, Error, void>({
    mutationKey: queryKeys.activities.all(),
    mutationFn: async () => {
      const job = await refreshActivities()
      return followIngestionJob(job.id)
    },
    onSettled: () => {
      void invalidateActivityData(client)
    },
  })
}
