import { computed, readonly, ref } from 'vue'

import type { AppConfig, FeatureFlags } from '@/features/config/types'

import { queryClient } from '@/plugins/vueQuery'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import { DEFAULT_APP_CONFIG, mapServerSettingsToAppConfig } from '@/features/config/services/config'
import { fetchPublicServerSettings } from '@/features/config/services/serverSettings'
import { useTelemetry } from '@/composables/useTelemetry'

const config = ref<AppConfig>(DEFAULT_APP_CONFIG)

/**
 * Set when the public server settings can't be reached at all — a network
 * failure, CORS block, or timeout rather than an HTTP error response. That
 * almost always means the runtime `ENDURAIN_HOST` points somewhere the browser
 * can't reach, so the app surfaces a blocking configuration screen instead of
 * silently booting on unreachable defaults.
 */
const configError = ref(false)

/**
 * Loads runtime configuration once during bootstrap, derived from the public
 * server settings (the single source of truth for per-instance flags). When
 * the settings are unreachable the app keeps its self-hosted defaults so it
 * still boots; that fallback is expected and stays quiet, so only unexpected
 * failures are reported.
 *
 * The fetched settings also seed the public-settings query, so the first screen
 * that reads them (the list page size, the login screen) does not request them
 * again.
 *
 * A reachable backend that answers with an HTTP error ({@link HttpError}) is
 * treated as a transient backend problem and stays quiet. Any other failure —
 * a `TypeError` ("Failed to fetch"), CORS block, or timeout — means the host
 * itself was unreachable, which is the signal that `ENDURAIN_HOST` is
 * misconfigured, so it raises {@link configError}.
 */
export async function loadAppConfig(): Promise<void> {
  configError.value = false
  try {
    const settings = await fetchPublicServerSettings()
    queryClient.setQueryData(queryKeys.public.serverSettings(), settings)
    config.value = mapServerSettingsToAppConfig(settings)
  } catch (error) {
    if (error instanceof HttpError) {
      return
    }
    configError.value = true
    useTelemetry().captureError(error, { scope: 'loadAppConfig', configError: true })
  }
}

/**
 * Exposes the runtime application configuration.
 *
 * @returns A read-only reactive {@link AppConfig} and the {@link configError}
 *   flag set when the backend host is unreachable at boot.
 */
export function useAppConfig() {
  return { config: readonly(config), configError: readonly(configError) }
}

/**
 * Exposes instance feature flags and a typed predicate helper.
 *
 * @returns The reactive `features` and an `isEnabled` checker.
 */
export function useFeatureFlags() {
  return {
    features: computed(() => config.value.features),
    /**
     * @param flag - The feature flag to check.
     * @returns Whether the flag is enabled on this instance.
     */
    isEnabled(flag: keyof FeatureFlags): boolean {
      return config.value.features[flag]
    },
  }
}
