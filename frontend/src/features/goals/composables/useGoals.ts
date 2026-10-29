import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { storeToRefs } from 'pinia'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { Goal, GoalFilters, GoalInput } from '@/features/goals/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { createGoal, deleteGoal, fetchGoals, updateGoal } from '@/features/goals/services/goals'

/**
 * The authenticated user's goals, narrowed by the active filters. Gated on
 * authentication so it never fires on the login screen. Keeps the previous
 * results visible while a filter change refetches.
 *
 * @param filters - The active goal filters (reactive).
 * @returns The TanStack Query result for the goals list.
 */
export function useGoalsQuery(filters: MaybeRefOrGetter<GoalFilters>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const resolvedFilters = computed(() => toValue(filters))

  return useQuery({
    queryKey: computed(() => queryKeys.goals.list({ ...resolvedFilters.value })),
    queryFn: ({ signal }) => fetchGoals(resolvedFilters.value, signal),
    enabled: isAuthenticated,
    placeholderData: keepPreviousData,
  })
}

/**
 * Create mutation. Invalidates every goals query on settle so the list refetches
 * the server-authoritative state.
 *
 * @returns The TanStack Query mutation for creating a goal.
 */
export function useCreateGoalMutation() {
  const client = useQueryClient()

  return useMutation<Goal, Error, GoalInput>({
    mutationKey: queryKeys.goals.all(),
    mutationFn: (input) => createGoal(input),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.goals.all() })
    },
  })
}

/**
 * Update mutation. Invalidates every goals query on settle.
 *
 * @returns The TanStack Query mutation for updating a goal.
 */
export function useUpdateGoalMutation() {
  const client = useQueryClient()

  return useMutation<Goal, Error, { id: number; input: GoalInput; version: number }>({
    mutationKey: queryKeys.goals.all(),
    mutationFn: ({ id, input, version }) => updateGoal(id, input, version),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.goals.all() })
    },
  })
}

/**
 * Delete mutation. Invalidates every goals query on settle.
 *
 * @returns The TanStack Query mutation for deleting a goal.
 */
export function useDeleteGoalMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, { id: number; version: number }>({
    mutationKey: queryKeys.goals.all(),
    mutationFn: ({ id, version }) => deleteGoal(id, version),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.goals.all() })
    },
  })
}
