import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { StreakSettings } from '@/features/streaks/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchMyWeeklyStreak,
  fetchStreakSettings,
  fetchUserWeeklyStreak,
  updateStreakSettings,
} from '@/features/streaks/services/streaks'

/**
 * The authenticated viewer's weekly streak (home dashboard and summary page).
 * Gated on authentication so it never fires on the login screen.
 *
 * @param enabled - Optional reactive gate ANDed with the auth gate.
 * @returns The TanStack Query result for the viewer's streak.
 */
export function useMyWeeklyStreakQuery(enabled: MaybeRefOrGetter<boolean> = true) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.activities.streak('me'),
    queryFn: ({ signal }) => fetchMyWeeklyStreak(signal),
    enabled: computed(() => toValue(enabled) && isAuthenticated.value),
  })
}

/**
 * A profile owner's weekly streak. Resolves to `null` when the owner keeps the
 * streak private, so the profile can simply hide the card.
 *
 * @param userId - Reactive id of the profile owner.
 * @returns The TanStack Query result for that user's streak.
 */
export function useUserWeeklyStreakQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  /** The owner id as a positive number, or `0` while unavailable (disables the query). */
  const id = computed(() => {
    const value = toValue(userId)
    return value !== null && Number.isFinite(value) && value > 0 ? value : 0
  })

  return useQuery({
    queryKey: computed(() => queryKeys.activities.streak(id.value)),
    queryFn: ({ signal }) => fetchUserWeeklyStreak(id.value, signal),
    enabled: computed(() => isAuthenticated.value && id.value > 0),
  })
}

/**
 * The authenticated user's streak settings.
 *
 * @returns The TanStack Query result for the settings.
 */
export function useStreakSettingsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.streakSettings.detail(),
    queryFn: ({ signal }) => fetchStreakSettings(signal),
    enabled: isAuthenticated,
  })
}

/**
 * Saves the streak settings. On success the settings cache is primed with the
 * stored value, and every streak query is invalidated so cards recalculate
 * with the new target and type filter.
 *
 * @returns The TanStack Query mutation for updating the settings.
 */
export function useUpdateStreakSettingsMutation() {
  const client = useQueryClient()

  return useMutation<StreakSettings, Error, StreakSettings>({
    mutationKey: queryKeys.streakSettings.detail(),
    mutationFn: (settings) => updateStreakSettings(settings),
    onSuccess: (stored) => {
      client.setQueryData(queryKeys.streakSettings.detail(), stored)
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ['activities', 'streak'] })
    },
  })
}
