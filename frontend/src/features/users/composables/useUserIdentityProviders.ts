import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { StepUpInput } from '@/features/security/types'
import type { UserIdentityProvider } from '@/features/users/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchUserIdentityProviders,
  unlinkUserIdentityProvider,
} from '@/features/users/services/identityProviders'

/**
 * A user's linked identity providers for the admin detail page. Gated on
 * authentication and a positive id (a bad route id keeps the query disabled).
 *
 * @param userId - Reactive target user id (or `null` before it resolves).
 * @returns The TanStack Query result for the user's identity-provider links.
 */
export function useUserIdentityProvidersQuery(userId: MaybeRefOrGetter<number | null>) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<UserIdentityProvider[]>({
    queryKey: computed(() => queryKeys.users.identityProviders(toValue(userId) ?? 0)),
    queryFn: ({ signal }) => fetchUserIdentityProviders(toValue(userId) as number, signal),
    enabled: computed(() => isAuthenticated.value && (toValue(userId) ?? 0) > 0),
  })
}

/**
 * Identity-provider unlink mutation. Invalidates the owner's provider list (so
 * the row drops out) plus the user detail and list — the external-auth badge and
 * count derive from the link count.
 *
 * @returns The TanStack Query mutation for unlinking a user's identity provider.
 */
export function useUnlinkUserIdentityProviderMutation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      userId,
      idpId,
      stepUp,
    }: {
      userId: number
      idpId: number
      stepUp: StepUpInput
    }) => unlinkUserIdentityProvider(userId, idpId, stepUp),
    onSuccess: (_data, { userId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.identityProviders(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.detail(userId) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.lists() })
    },
  })
}
