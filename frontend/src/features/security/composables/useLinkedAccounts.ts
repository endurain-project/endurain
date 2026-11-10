import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { StepUpInput } from '@/features/security/types'

import { queryKeys } from '@/services/queryKeys'
import { fetchEnabledIdentityProviders } from '@/services/identityProviders'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  fetchLinkedProviders,
  startProviderLink,
  unlinkProvider,
} from '@/features/security/services/linkedAccounts'

/** Cache lifetime for the available-providers list (build-time constant). */
const AVAILABLE_PROVIDERS_STALE_TIME = 5 * 60_000

/**
 * The authenticated user's linked identity providers. Gated on authentication.
 *
 * @returns The TanStack Query result for the linked providers.
 */
export function useLinkedProvidersQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.security.linkedProviders(),
    queryFn: ({ signal }) => fetchLinkedProviders(signal),
    enabled: isAuthenticated,
  })
}

/**
 * The enabled providers a user could link to. Shares the public-providers cache
 * key with the login screen so the list is fetched once per window.
 *
 * @returns The TanStack Query result for the available providers.
 */
export function useAvailableProvidersQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.public.identityProviders(),
    queryFn: () => fetchEnabledIdentityProviders(),
    enabled: isAuthenticated,
    staleTime: AVAILABLE_PROVIDERS_STALE_TIME,
  })
}

/**
 * Unlink mutation. Invalidates the linked-providers and public-providers caches
 * on success so both lists reflect the change, and the known devices, which an
 * unlink forgets as a security change.
 *
 * @returns The TanStack Query mutation for unlinking a provider.
 */
export function useUnlinkProviderMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, { idpId: number; input: StepUpInput }>({
    mutationKey: queryKeys.security.all(),
    mutationFn: ({ idpId, input }) => unlinkProvider(idpId, input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.security.linkedProviders() })
      void client.invalidateQueries({ queryKey: queryKeys.public.identityProviders() })
      void client.invalidateQueries({ queryKey: queryKeys.security.devices() })
    },
  })
}

/**
 * Start-link mutation. Resolves to the provider's authorization URL; the caller
 * then navigates the browser there to begin the OAuth round-trip.
 *
 * @returns The TanStack Query mutation for starting a provider link.
 */
export function useStartProviderLinkMutation() {
  return useMutation<
    string,
    Error,
    { idpId: number; input: StepUpInput; revokeOtherSessions: boolean }
  >({
    mutationKey: queryKeys.security.all(),
    mutationFn: ({ idpId, input, revokeOtherSessions }) =>
      startProviderLink(idpId, input, revokeOtherSessions),
  })
}
