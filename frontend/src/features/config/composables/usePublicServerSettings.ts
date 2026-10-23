import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'

import type { IdentityProviderPublic } from '@/types'

import { queryClient } from '@/plugins/vueQuery'
import { fetchEnabledIdentityProviders } from '@/services/identityProviders'
import { queryKeys } from '@/services/queryKeys'
import { getApiBaseUrl } from '@/services/runtime'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'
import defaultLoginImage from '@/assets/login.png'

/** Shared cache lifetime so every auth screen reuses one fetch per window. */
const PUBLIC_SETTINGS_STALE_TIME = 5 * 60_000

/**
 * Loads the public server settings and SSO providers needed by the
 * unauthenticated auth screens (login, sign-up, password reset). Failures
 * fall back to safe defaults so the auth screen always renders.
 *
 * @returns Reactive settings/providers state, the resolved login image, and a
 *   `load` action that awaits both requests.
 */
export function usePublicServerSettings() {
  // Use `placeholderData`, never `initialData`: `initialData` is written to the
  // query cache and, paired with a `staleTime`, is treated as a fresh fetch.
  // That suppresses the real request on mount and makes `ensureQueryData()` in
  // `load()` return the seeded defaults (`sso_enabled: false`), so `/public/idp`
  // is never called. `placeholderData` renders the same safe defaults while the
  // real settings are fetched.
  const settingsQuery = useQuery({
    queryKey: queryKeys.public.serverSettings(),
    queryFn: fetchPublicServerSettings,
    placeholderData: DEFAULT_PUBLIC_SERVER_SETTINGS,
    retry: 1,
    staleTime: PUBLIC_SETTINGS_STALE_TIME,
  })

  const serverSettings = computed(() => settingsQuery.data.value ?? DEFAULT_PUBLIC_SERVER_SETTINGS)

  const ssoProvidersQuery = useQuery<IdentityProviderPublic[]>({
    queryKey: queryKeys.public.identityProviders(),
    queryFn: fetchEnabledIdentityProviders,
    // Only fetch providers once settings confirm SSO is enabled; flips on
    // reactively when the settings response arrives.
    enabled: computed(() => serverSettings.value.sso_enabled),
    // `placeholderData` (not `initialData`) so enabling the query actually
    // triggers the `/public/idp` fetch instead of reusing a cached empty list.
    placeholderData: [],
    retry: 1,
    staleTime: PUBLIC_SETTINGS_STALE_TIME,
  })

  const ssoProviders = computed(() =>
    serverSettings.value.sso_enabled ? (ssoProvidersQuery.data.value ?? []) : [],
  )
  const isSettingsLoading = computed(() => settingsQuery.isFetching.value)
  const isSsoLoading = computed(
    () => serverSettings.value.sso_enabled && ssoProvidersQuery.isFetching.value,
  )

  /** Instance login photo when configured, else the bundled default image. */
  const loginImageUrl = computed(() =>
    serverSettings.value.login_photo_set
      ? `${getApiBaseUrl()}/public/server-settings/login-photo`
      : defaultLoginImage,
  )

  /**
   * Ensures public server settings are cached, then enabled SSO providers when
   * SSO is on. Backed by TanStack Query's cache, so concurrent auth screens
   * share one response, retries, and request de-duplication, and the awaited
   * result lets callers branch on the resolved settings.
   */
  async function load(): Promise<void> {
    const settings = await queryClient.ensureQueryData({
      queryKey: queryKeys.public.serverSettings(),
      queryFn: fetchPublicServerSettings,
      staleTime: PUBLIC_SETTINGS_STALE_TIME,
    })

    if (!settings.sso_enabled) {
      return
    }

    await queryClient.ensureQueryData({
      queryKey: queryKeys.public.identityProviders(),
      queryFn: fetchEnabledIdentityProviders,
      staleTime: PUBLIC_SETTINGS_STALE_TIME,
    })
  }

  return { serverSettings, ssoProviders, isSettingsLoading, isSsoLoading, loginImageUrl, load }
}
