import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { ApiKey, StepUpInput } from '@/features/security/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchUserApiKeys,
  revokeAllUserApiKeys,
  revokeUserApiKey,
} from '@/features/users/services/apiKeys'

/**
 * A user's API keys for the admin detail page. Gated on authentication and a
 * positive id (a bad route id keeps the query disabled).
 *
 * @param userId - Reactive target user id (or `null` before it resolves).
 * @returns The TanStack Query result for the user's API keys.
 */
export function useUserApiKeysQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<ApiKey[]>({
    queryKey: computed(() => queryKeys.users.apiKeys(toValue(userId) ?? 0)),
    queryFn: ({ signal }) => fetchUserApiKeys(toValue(userId) as number, signal),
    enabled: computed(() => isAuthenticated.value && (toValue(userId) ?? 0) > 0),
  })
}

/**
 * Revokes one API key of a user. Invalidates the owner's list on settle so it shows
 * the server state, including after a 404 for a key that no longer exists.
 *
 * @returns The TanStack Query mutation for revoking a user's API key.
 */
export function useRevokeUserApiKeyMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      apiKeyId,
      userId,
      stepUp,
    }: {
      apiKeyId: string
      userId: number
      stepUp: StepUpInput
    }) => revokeUserApiKey(apiKeyId, userId, stepUp),
    onSettled: (_data, _error, { userId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.apiKeys(userId) })
    },
  })
}

/**
 * Revokes every active API key of a user. Invalidates the owner's list on settle.
 *
 * @returns The TanStack Query mutation for revoking all of a user's API keys.
 */
export function useRevokeAllUserApiKeysMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userId, stepUp }: { userId: number; stepUp: StepUpInput }) =>
      revokeAllUserApiKeys(userId, stepUp),
    onSettled: (_data, _error, { userId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.apiKeys(userId) })
    },
  })
}
