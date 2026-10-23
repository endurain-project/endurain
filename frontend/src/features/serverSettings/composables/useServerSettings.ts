import { storeToRefs } from 'pinia'
import { computed, type Ref } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'

import type {
  EmailStatusDto,
  LogFilters,
  LogPage,
  LogsStatusDto,
  MailSettings,
  MailSettingsUpdate,
  ServerSettings,
  ServerSettingsUpdate,
} from '@/features/serverSettings/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import {
  clearLogs,
  deleteLoginPhoto,
  downloadLogs,
  fetchEmailStatus,
  fetchLogs,
  fetchLogsStatus,
  fetchMailSettings,
  fetchServerSettings,
  fetchTileMapsTemplates,
  sendTestEmail,
  updateMailSettings,
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

  return useMutation<ServerSettings, Error, ServerSettingsUpdate>({
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
 * the current state.
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

/**
 * The editable mail server settings (admin scope). Always refetched on mount so
 * the form never seeds from stale env-managed flags.
 *
 * @returns The TanStack Query result for the mail settings.
 */
export function useMailSettingsQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<MailSettings>({
    queryKey: queryKeys.serverSettings.mail(),
    queryFn: ({ signal }) => fetchMailSettings(signal),
    enabled: isAuthenticated,
    staleTime: 0,
  })
}

/**
 * Update mutation for the mail server settings. Invalidates the settings and the
 * email status, since whether email is usable depends on the settings.
 *
 * @returns The TanStack Query mutation for updating the mail settings.
 */
export function useUpdateMailSettingsMutation() {
  const client = useQueryClient()

  return useMutation<MailSettings, Error, MailSettingsUpdate>({
    mutationKey: queryKeys.serverSettings.mail(),
    mutationFn: (settings) => updateMailSettings(settings),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.serverSettings.mail() })
      void client.invalidateQueries({ queryKey: queryKeys.serverSettings.email() })
    },
  })
}

/** Most records the log viewer keeps in memory while tailing. */
const MAX_LOG_ENTRIES = 1000

/** How often a live tail asks for new records, in milliseconds. */
const LOG_TAIL_INTERVAL_MS = 3000

/**
 * Whether the server-log viewer is available. A failure (for example a token
 * that predates the logs scope) counts as unavailable.
 *
 * @returns The TanStack Query result for the viewer status.
 */
export function useLogsStatusQuery() {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useQuery<LogsStatusDto>({
    queryKey: queryKeys.serverSettings.logsStatus(),
    queryFn: ({ signal }) => fetchLogsStatus(signal),
    enabled: isAuthenticated,
    retry: false,
  })
}

/**
 * The server-log tail for the given filters. The first fetch returns the
 * newest records; every later fetch asks only for what was written since the
 * last cursor and appends it, so a refetch (manual or live) extends the list.
 * A cursor that moved backwards means the log rotated, which restarts the list.
 *
 * @param filters - Severity and text filters; a change starts a new tail.
 * @param live - Whether to keep polling for new records.
 * @returns The TanStack Query result for the accumulated log page.
 */
export function useLogsQuery(filters: Ref<LogFilters>, live: Ref<boolean>) {
  const client = useQueryClient()
  const queryKey = computed(() =>
    queryKeys.serverSettings.logs(filters.value.level, filters.value.search),
  )

  return useQuery<LogPage>({
    queryKey,
    queryFn: async ({ signal }) => {
      const previous = client.getQueryData<LogPage>(queryKey.value)
      const page = await fetchLogs(filters.value, previous?.cursor ?? null, signal)
      if (!previous || page.cursor < previous.cursor) {
        return page
      }
      return {
        entries: [...previous.entries, ...page.entries].slice(-MAX_LOG_ENTRIES),
        cursor: page.cursor,
      }
    },
    refetchInterval: () => (live.value ? LOG_TAIL_INTERVAL_MS : false),
    staleTime: 0,
    gcTime: 0,
  })
}

/**
 * Download mutation. Resolves with the log file; the caller saves it (e.g. via
 * `downloadBlob`). Modelled as a mutation purely for the in-flight / error
 * state — it changes no server state.
 *
 * @returns The TanStack Query mutation that produces the log file blob.
 */
export function useDownloadLogsMutation() {
  return useMutation<Blob, Error, void>({
    mutationFn: () => downloadLogs(),
  })
}

/**
 * Clear mutation. Resets every cached log tail, since the file they were read
 * from is gone and their cursors no longer point into it.
 *
 * @returns The TanStack Query mutation for clearing the server log.
 */
export function useClearLogsMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, void>({
    mutationFn: () => clearLogs(),
    onSuccess: () => client.resetQueries({ queryKey: queryKeys.serverSettings.logsAll() }),
  })
}
