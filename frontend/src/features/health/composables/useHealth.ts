/**
 * TanStack Query composables for the health area. Both queries are gated on
 * authentication and keyed under the centralized `health` domain so a future
 * targets write can cascade to the dashboard via a broad invalidation.
 */

import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  FastingEntry,
  FastingEntryInput,
  FastingStatus,
  HealthInterval,
  PoopEntry,
  PoopEntryInput,
  SleepEntry,
  SleepEntryInput,
  StepsEntry,
  StepsEntryInput,
  WaterEntry,
  WaterEntryInput,
  WeightEntry,
  WeightEntryInput,
  WeightInterval,
} from '@/features/health/types'

import { queryKeys } from '@/services/queryKeys'
import { useInvalidatingMutation } from '@/composables/useInvalidatingMutation'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  createStepsEntry,
  createWaterEntry,
  createWeightEntry,
  createPoopEntry,
  createFastingEntry,
  createSleepEntry,
  completeFastingEntry,
  deleteStepsEntry,
  deleteWaterEntry,
  deleteWeightEntry,
  deletePoopEntry,
  deleteFastingEntry,
  deleteSleepEntry,
  fetchActiveFasting,
  fetchFastingEntries,
  fetchFastingStats,
  fetchHealthDashboard,
  fetchHealthTargets,
  fetchStepsEntries,
  fetchWaterEntries,
  fetchWeightEntries,
  fetchPoopEntries,
  fetchRhrEntries,
  fetchSleepEntries,
  updateStepsEntry,
  updateStepsTarget,
  updateWaterEntry,
  updateWaterTarget,
  updateWeightEntry,
  updateWeightTarget,
  updatePoopEntry,
  updatePoopTarget,
  updateFastingEntry,
  updateFastingTarget,
  updateSleepEntry,
  updateSleepTarget,
} from '@/features/health/services/health'

/** Freshness window for mutable health reads; health writes and sync events invalidate them. */
const HEALTH_QUERY_STALE_TIME_MS = 60_000

/**
 * The authenticated user's health targets, used to annotate each dashboard card
 * with its metric's target and direction. Gated on authentication.
 *
 * @returns The TanStack Query result for the user's health targets.
 */
export function useHealthTargetsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.health.targets(),
    queryFn: ({ signal }) => fetchHealthTargets(signal),
    staleTime: HEALTH_QUERY_STALE_TIME_MS,
    enabled: isAuthenticated,
  })
}

/**
 * The authenticated user's consolidated daily health dashboard and health targets.
 * The response also seeds the targets query cache for other health views.
 *
 * @returns The TanStack Query result for the dashboard and targets.
 */
export function useHealthDashboardQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const client = useQueryClient()

  return useQuery({
    queryKey: queryKeys.health.dashboard(),
    queryFn: async ({ signal }) => {
      const dashboard = await fetchHealthDashboard(signal)
      if (dashboard.targets) {
        client.setQueryData(queryKeys.health.targets(), dashboard.targets)
      }
      return dashboard
    },
    staleTime: HEALTH_QUERY_STALE_TIME_MS,
    enabled: isAuthenticated,
  })
}

/** Shared page/filter shape for paginated health-history queries. */
interface HealthEntriesParams<Interval extends string> {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
  /** Time window to filter the history to. */
  interval: Interval
}

/** Variables for update-entry mutations shared by CRUD health metrics. */
interface UpdateEntryVariables<Input> {
  /** Record id to update. */
  id: number
  /** Clean metric input. */
  input: Input
  /** The row version the form was loaded at, for `If-Match`. */
  version: number
}

/** Standard paginated query wrapper for health-history zones. */
function useHealthEntriesQuery<Page, Interval extends string>(
  keyForFilters: (filters: Record<string, unknown>) => readonly unknown[],
  fetchEntries: (params: HealthEntriesParams<Interval>, signal?: AbortSignal) => Promise<Page>,
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<Interval>,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: computed(() =>
      keyForFilters({
        page: toValue(page),
        numRecords: toValue(pageSize),
        interval: toValue(interval),
      }),
    ),
    queryFn: ({ signal }) =>
      fetchEntries(
        {
          page: toValue(page),
          numRecords: toValue(pageSize),
          interval: toValue(interval),
        },
        signal,
      ),
    staleTime: HEALTH_QUERY_STALE_TIME_MS,
    placeholderData: keepPreviousData,
    enabled: isAuthenticated,
  })
}

/** Standard create-entry mutation wrapper for health CRUD zones. */
function useCreateHealthEntryMutation<Entry, Input>(
  mutationKey: readonly unknown[],
  createEntry: (input: Input) => Promise<Entry>,
) {
  return useInvalidatingMutation<Entry, Input>({
    mutationKey,
    mutationFn: (input) => createEntry(input),
    invalidateKey: queryKeys.health.all(),
  })
}

/** Standard update-entry mutation wrapper for health CRUD zones. */
function useUpdateHealthEntryMutation<Entry, Input>(
  mutationKey: readonly unknown[],
  updateEntry: (id: number, input: Input, version: number) => Promise<Entry>,
) {
  return useInvalidatingMutation<Entry, UpdateEntryVariables<Input>>({
    mutationKey,
    mutationFn: ({ id, input, version }) => updateEntry(id, input, version),
    invalidateKey: queryKeys.health.all(),
  })
}

/** Standard delete-entry mutation wrapper for health CRUD zones. */
function useDeleteHealthEntryMutation(
  mutationKey: readonly unknown[],
  deleteEntry: (id: number) => Promise<void>,
) {
  return useInvalidatingMutation<void, number>({
    mutationKey,
    mutationFn: (id) => deleteEntry(id),
    invalidateKey: queryKeys.health.all(),
  })
}

/** Standard target-update mutation wrapper for health zones. */
function useHealthTargetMutation<TVariables>(
  updateTarget: (variables: TVariables) => Promise<unknown>,
) {
  return useInvalidatingMutation<unknown, TVariables>({
    mutationKey: queryKeys.health.targets(),
    mutationFn: (variables) => updateTarget(variables),
    invalidateKey: queryKeys.health.all(),
  })
}

/**
 * One page of the authenticated user's weight history, filtered to the chosen
 * interval. Keyed on page + size + interval; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on auth.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current weight-history page.
 */
export function useWeightEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<WeightInterval>,
) {
  return useHealthEntriesQuery(
    queryKeys.health.weight,
    fetchWeightEntries,
    page,
    pageSize,
    interval,
  )
}

/**
 * Create-weight mutation. Invalidates the health domain on settle so the
 * weight history, dashboard, and targets refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a weight entry.
 */
export function useCreateWeightEntryMutation() {
  return useCreateHealthEntryMutation<WeightEntry, WeightEntryInput>(
    queryKeys.health.weightLists(),
    createWeightEntry,
  )
}

/**
 * Update-weight mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a weight entry.
 */
export function useUpdateWeightEntryMutation() {
  return useUpdateHealthEntryMutation<WeightEntry, WeightEntryInput>(
    queryKeys.health.weightLists(),
    updateWeightEntry,
  )
}

/**
 * Delete-weight mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a weight entry.
 */
export function useDeleteWeightEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.weightLists(), deleteWeightEntry)
}

/**
 * Update-weight-target mutation. Invalidates the health domain on settle so the
 * dashboard's weight card and the weight zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the weight target.
 */
export function useUpdateWeightTargetMutation() {
  return useHealthTargetMutation<{ version: number; weightKg: number | null }>(
    ({ version, weightKg }) => updateWeightTarget(version, weightKg),
  )
}

/**
 * One page of the authenticated user's steps history, filtered to the chosen
 * interval. Keyed on page + size + interval; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on auth.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current steps-history page.
 */
export function useStepsEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(queryKeys.health.steps, fetchStepsEntries, page, pageSize, interval)
}

/**
 * Create-steps mutation. Invalidates the health domain on settle so the steps
 * history, dashboard, and targets refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a steps entry.
 */
export function useCreateStepsEntryMutation() {
  return useCreateHealthEntryMutation<StepsEntry, StepsEntryInput>(
    queryKeys.health.stepsLists(),
    createStepsEntry,
  )
}

/**
 * Update-steps mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a steps entry.
 */
export function useUpdateStepsEntryMutation() {
  return useUpdateHealthEntryMutation<StepsEntry, StepsEntryInput>(
    queryKeys.health.stepsLists(),
    updateStepsEntry,
  )
}

/**
 * Delete-steps mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a steps entry.
 */
export function useDeleteStepsEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.stepsLists(), deleteStepsEntry)
}

/**
 * Update-steps-target mutation. Invalidates the health domain on settle so the
 * dashboard's steps card and the steps zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the steps target.
 */
export function useUpdateStepsTargetMutation() {
  return useHealthTargetMutation<{ version: number; steps: number | null }>(({ version, steps }) =>
    updateStepsTarget(version, steps),
  )
}

/**
 * One page of the authenticated user's water history, filtered to the chosen
 * interval. Keyed on page + size + interval; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on auth.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current water-history page.
 */
export function useWaterEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(queryKeys.health.water, fetchWaterEntries, page, pageSize, interval)
}

/**
 * Create-water mutation. Invalidates the health domain on settle so the water
 * history, dashboard, and targets refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a water entry.
 */
export function useCreateWaterEntryMutation() {
  return useCreateHealthEntryMutation<WaterEntry, WaterEntryInput>(
    queryKeys.health.waterLists(),
    createWaterEntry,
  )
}

/**
 * Update-water mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a water entry.
 */
export function useUpdateWaterEntryMutation() {
  return useUpdateHealthEntryMutation<WaterEntry, WaterEntryInput>(
    queryKeys.health.waterLists(),
    updateWaterEntry,
  )
}

/**
 * Delete-water mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a water entry.
 */
export function useDeleteWaterEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.waterLists(), deleteWaterEntry)
}

/**
 * Update-water-target mutation. Invalidates the health domain on settle so the
 * dashboard's water card and the water zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the water target.
 */
export function useUpdateWaterTargetMutation() {
  return useHealthTargetMutation<{ version: number; waterMl: number | null }>(
    ({ version, waterMl }) => updateWaterTarget(version, waterMl),
  )
}

/**
 * One page of the authenticated user's bowel-movement history, filtered to the
 * chosen interval. Keyed on page + size + interval; uses `keepPreviousData` so
 * paging keeps the current rows visible until the next page resolves. Gated on
 * authentication.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current poop-history page.
 */
export function usePoopEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(queryKeys.health.poop, fetchPoopEntries, page, pageSize, interval)
}

/**
 * Create-poop mutation. Invalidates the health domain on settle so the poop
 * history, dashboard, and targets refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a poop entry.
 */
export function useCreatePoopEntryMutation() {
  return useCreateHealthEntryMutation<PoopEntry, PoopEntryInput>(
    queryKeys.health.poopLists(),
    createPoopEntry,
  )
}

/**
 * Update-poop mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a poop entry.
 */
export function useUpdatePoopEntryMutation() {
  return useUpdateHealthEntryMutation<PoopEntry, PoopEntryInput>(
    queryKeys.health.poopLists(),
    updatePoopEntry,
  )
}

/**
 * Delete-poop mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a poop entry.
 */
export function useDeletePoopEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.poopLists(), deletePoopEntry)
}

/**
 * Update-poop-target mutation. Invalidates the health domain on settle so the
 * dashboard's bowel-movement card and the poop zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the poop target.
 */
export function useUpdatePoopTargetMutation() {
  return useHealthTargetMutation<{ version: number; poopCount: number | null }>(
    ({ version, poopCount }) => updatePoopTarget(version, poopCount),
  )
}

/**
 * One page of the authenticated user's resting-heart-rate history, filtered to
 * the chosen interval. RHR is a read-only view derived from the sleep records,
 * so this zone exposes only a query (no mutations). Keyed on page + size +
 * interval; uses `keepPreviousData` so paging keeps the current rows visible
 * until the next page resolves. Gated on authentication.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current resting-heart-rate page.
 */
export function useRhrEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(queryKeys.health.rhr, fetchRhrEntries, page, pageSize, interval)
}

/**
 * One page of the authenticated user's fasting history, filtered to the chosen
 * interval. Keyed on page + size + interval; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on auth.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current fasting-history page.
 */
export function useFastingEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(
    queryKeys.health.fasting,
    fetchFastingEntries,
    page,
    pageSize,
    interval,
  )
}

/**
 * The authenticated user's active (in-progress) fasting session, or `null` when
 * none is running. Drives the live timer card. Gated on authentication.
 *
 * @returns The TanStack Query result for the active fasting session.
 */
export function useActiveFastingQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.health.fastingActive(),
    queryFn: ({ signal }) => fetchActiveFasting(signal),
    staleTime: HEALTH_QUERY_STALE_TIME_MS,
    enabled: isAuthenticated,
  })
}

/**
 * The authenticated user's aggregate fasting statistics (streaks, totals,
 * completion rate) shown above the history. Gated on authentication.
 *
 * @returns The TanStack Query result for the fasting statistics.
 */
export function useFastingStatsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.health.fastingStats(),
    queryFn: ({ signal }) => fetchFastingStats(signal),
    staleTime: HEALTH_QUERY_STALE_TIME_MS,
    enabled: isAuthenticated,
  })
}

/**
 * Start-fasting mutation. Invalidates the health domain on settle so the active
 * session, stats, history, and dashboard refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for starting a fasting session.
 */
export function useCreateFastingEntryMutation() {
  return useCreateHealthEntryMutation<FastingEntry, FastingEntryInput>(
    queryKeys.health.fastingLists(),
    createFastingEntry,
  )
}

/**
 * Update-fasting mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a fasting session.
 */
export function useUpdateFastingEntryMutation() {
  return useUpdateHealthEntryMutation<FastingEntry, FastingEntryInput>(
    queryKeys.health.fastingLists(),
    updateFastingEntry,
  )
}

/**
 * Complete-fasting mutation. Ends the active fast with the given status and
 * invalidates the health domain on settle so the timer card clears and the
 * stats/history refresh.
 *
 * @returns The TanStack Query mutation for completing a fasting session.
 */
export function useCompleteFastingEntryMutation() {
  return useInvalidatingMutation<
    FastingEntry,
    { id: number; fastEndTime: string; status: FastingStatus }
  >({
    mutationKey: queryKeys.health.fastingLists(),
    mutationFn: ({ id, fastEndTime, status }) => completeFastingEntry(id, fastEndTime, status),
    invalidateKey: queryKeys.health.all(),
  })
}

/**
 * Delete-fasting mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a fasting session.
 */
export function useDeleteFastingEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.fastingLists(), deleteFastingEntry)
}

/**
 * Update-fasting-target mutation. Invalidates the health domain on settle so the
 * dashboard's fasting card and the fasting zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the fasting target.
 */
export function useUpdateFastingTargetMutation() {
  return useHealthTargetMutation<{
    version: number
    fastingSeconds: number | null
  }>(({ version, fastingSeconds }) => updateFastingTarget(version, fastingSeconds))
}

/**
 * One page of the authenticated user's sleep history, filtered to the chosen
 * interval. Keyed on page + size + interval; uses `keepPreviousData` so paging
 * keeps the current rows visible until the next page resolves. Gated on auth.
 *
 * @param page - Reactive 1-based page number.
 * @param pageSize - Reactive records-per-page (from server settings).
 * @param interval - Reactive time window to filter the history to.
 * @returns The TanStack Query result for the current sleep-history page.
 */
export function useSleepEntriesQuery(
  page: MaybeRefOrGetter<number>,
  pageSize: MaybeRefOrGetter<number>,
  interval: MaybeRefOrGetter<HealthInterval>,
) {
  return useHealthEntriesQuery(queryKeys.health.sleep, fetchSleepEntries, page, pageSize, interval)
}

/**
 * Create-sleep mutation. Invalidates the health domain on settle so the sleep
 * history, dashboard, and RHR zone refetch the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a sleep entry.
 */
export function useCreateSleepEntryMutation() {
  return useCreateHealthEntryMutation<SleepEntry, SleepEntryInput>(
    queryKeys.health.sleepLists(),
    createSleepEntry,
  )
}

/**
 * Update-sleep mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for updating a sleep entry.
 */
export function useUpdateSleepEntryMutation() {
  return useUpdateHealthEntryMutation<SleepEntry, SleepEntryInput>(
    queryKeys.health.sleepLists(),
    updateSleepEntry,
  )
}

/**
 * Delete-sleep mutation. Invalidates the health domain on settle.
 *
 * @returns The TanStack Query mutation for deleting a sleep entry.
 */
export function useDeleteSleepEntryMutation() {
  return useDeleteHealthEntryMutation(queryKeys.health.sleepLists(), deleteSleepEntry)
}

/**
 * Update-sleep-target mutation. Invalidates the health domain on settle so the
 * dashboard's sleep card and the sleep zone reflect the new target.
 *
 * @returns The TanStack Query mutation for updating the sleep target.
 */
export function useUpdateSleepTargetMutation() {
  return useHealthTargetMutation<{
    version: number
    sleepSeconds: number | null
  }>(({ version, sleepSeconds }) => updateSleepTarget(version, sleepSeconds))
}
