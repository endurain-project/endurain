import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { IdentityProvider, IdentityProviderInput } from '@/features/identityProviders/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  createIdentityProvider,
  deleteIdentityProvider,
  fetchIdentityProviders,
  fetchIdentityProviderTemplates,
  updateIdentityProvider,
} from '@/features/identityProviders/services/identityProviders'

/**
 * All configured identity providers (admin). Gated on authentication; the route
 * guard already restricts the page to admins.
 *
 * @returns The TanStack Query result for the providers list.
 */
export function useIdentityProvidersQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.identityProviders.list(),
    queryFn: ({ signal }) => fetchIdentityProviders(signal),
    enabled: isAuthenticated,
  })
}

/**
 * The static catalogue of provider presets. Cached indefinitely since the list
 * is build-time constant on the backend.
 *
 * @returns The TanStack Query result for the provider presets.
 */
export function useIdentityProviderTemplatesQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.identityProviders.templates(),
    queryFn: ({ signal }) => fetchIdentityProviderTemplates(signal),
    enabled: isAuthenticated,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

/**
 * Invalidates both the admin providers list and the public providers cache.
 * Enabling/disabling or editing a provider changes the unauthenticated login
 * screen's SSO buttons, so a write must refresh both.
 *
 * @param client - The active query client.
 */
function invalidateIdentityProviders(client: ReturnType<typeof useQueryClient>): void {
  void client.invalidateQueries({ queryKey: queryKeys.identityProviders.all() })
  void client.invalidateQueries({ queryKey: queryKeys.public.identityProviders() })
}

/**
 * Create mutation. Invalidates the admin and public caches on settle.
 *
 * @returns The TanStack Query mutation for creating a provider.
 */
export function useCreateIdentityProviderMutation() {
  const client = useQueryClient()

  return useMutation<IdentityProvider, Error, IdentityProviderInput>({
    mutationKey: queryKeys.identityProviders.all(),
    mutationFn: (input) => createIdentityProvider(input),
    onSettled: () => invalidateIdentityProviders(client),
  })
}

/**
 * Update mutation (also used for the inline enable/disable toggle). Invalidates
 * the admin and public caches on settle.
 *
 * @returns The TanStack Query mutation for updating a provider.
 */
export function useUpdateIdentityProviderMutation() {
  const client = useQueryClient()

  return useMutation<
    IdentityProvider,
    Error,
    { id: number; input: IdentityProviderInput; version: number }
  >({
    mutationKey: queryKeys.identityProviders.all(),
    mutationFn: ({ id, input, version }) => updateIdentityProvider(id, input, version),
    onSettled: () => invalidateIdentityProviders(client),
  })
}

/**
 * Delete mutation. Invalidates the admin and public caches on settle.
 *
 * @returns The TanStack Query mutation for deleting a provider.
 */
export function useDeleteIdentityProviderMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, { id: number; version: number }>({
    mutationKey: queryKeys.identityProviders.all(),
    mutationFn: ({ id, version }) => deleteIdentityProvider(id, version),
    onSettled: () => invalidateIdentityProviders(client),
  })
}
