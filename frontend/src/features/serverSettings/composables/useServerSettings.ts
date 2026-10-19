import { storeToRefs } from 'pinia'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type { EmailStatusDto, ServerSettings } from '@/features/serverSettings/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  deleteLoginPhoto,
  fetchEmailStatus,
  fetchServerSettings,
  fetchTileMapsTemplates,
  sendTestEmail,
  updateServerSettings,
  uploadLoginPhoto,
} from '@/features/serverSettings/services/serverSettings'

/**
 * The singleton server settings (admin scope). Gated on authentication; the
 * route guard already restricts the page to admins, so this only needs the
 * auth gate to avoid firing before a session exists.
 *
 * @returns The TanStack Query result for the server settings.
 */
export function useServerSettingsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.serverSettings.detail(),
    queryFn: ({ signal }) => fetchServerSettings(signal),
    enabled: isAuthenticated,
  })
}

/**
 * The static catalogue of tile-server presets. Cached indefinitely
 * (`staleTime: Infinity`) since the list is build-time constant on the backend.
 *
 * @returns The TanStack Query result for the tile-map presets.
 */
export function useTileMapsTemplatesQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery({
    queryKey: queryKeys.serverSettings.tileTemplates(),
    queryFn: ({ signal }) => fetchTileMapsTemplates(signal),
    enabled: isAuthenticated,
    staleTime: Number.POSITIVE_INFINITY,
  })
}

/**
 * Invalidates both the admin server-settings cache and the public settings
 * cache. Server settings drive unauthenticated surfaces too (the login screen's
 * photo, the list page size via `useRecordsPerPage`), so a write must refresh
 * both or those views go stale until reload.
 *
 * @param client - The active query client.
 */
function invalidateServerSettings(client: ReturnType<typeof useQueryClient>): void {
  void client.invalidateQueries({ queryKey: queryKeys.serverSettings.all() })
  void client.invalidateQueries({ queryKey: queryKeys.public.serverSettings() })
}

/**
 * Update mutation for the whole server-settings record. Invalidates the admin
 * and public caches on settle so the form, the login screen, and paginated
 * lists all pick up the new values.
 *
 * @returns The TanStack Query mutation for updating server settings.
 */
export function useUpdateServerSettingsMutation() {
  const client = useQueryClient()

  return useMutation<ServerSettings, Error, ServerSettings>({
    mutationKey: queryKeys.serverSettings.all(),
    mutationFn: (settings) => updateServerSettings(settings),
    onSettled: () => invalidateServerSettings(client),
  })
}

/**
 * Login-photo upload mutation. Invalidates the admin and public caches so the
 * "photo set" state and the login screen refresh.
 *
 * @returns The TanStack Query mutation for uploading the login photo.
 */
export function useUploadLoginPhotoMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, File>({
    mutationKey: queryKeys.serverSettings.all(),
    mutationFn: (file) => uploadLoginPhoto(file),
    onSettled: () => invalidateServerSettings(client),
  })
}

/**
 * Login-photo deletion mutation. Invalidates the same caches as the upload.
 *
 * @returns The TanStack Query mutation for removing the login photo.
 */
export function useDeleteLoginPhotoMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, void>({
    mutationKey: queryKeys.serverSettings.all(),
    mutationFn: () => deleteLoginPhoto(),
    onSettled: () => invalidateServerSettings(client),
  })
}

/**
 * Whether outgoing email is usable. Always refetched on mount so the admin sees
 * the current state after fixing their SMTP environment and restarting.
 *
 * @returns The TanStack Query result for the email status.
 */
export function useEmailStatusQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<EmailStatusDto>({
    queryKey: queryKeys.serverSettings.email(),
    queryFn: ({ signal }) => fetchEmailStatus(signal),
    enabled: isAuthenticated,
    staleTime: 0,
  })
}

/**
 * Sends a test email to the calling admin. Resolves with the confirmation
 * message; rejects with an `HttpError` whose detail carries the failure.
 *
 * @returns The TanStack Query mutation for the test email.
 */
export function useSendTestEmailMutation() {
  return useMutation<string, Error, void>({
    mutationFn: () => sendTestEmail(),
  })
}
