import type { AppConfig, PublicServerSettings } from '@/features/config/types'

import { fetchPublicServerSettings } from './serverSettings'

/**
 * Self-hosted defaults applied when the public server settings are
 * unreachable, so the app always boots.
 */
export const DEFAULT_APP_CONFIG: AppConfig = {
  features: {
    signUp: false,
    strava: true,
    garmin: true,
    federation: false,
  },
  branding: {
    appName: 'Endurain',
  },
  map: {
    tileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  },
  enabledLocales: null,
}

/**
 * Derives the app-wide runtime config from the public server settings — the
 * single source of truth for per-instance flags. Fields the public settings
 * don't yet carry (branding, integration availability, federation, enabled
 * locales) keep their self-hosted defaults until the backend exposes them, so
 * the {@link AppConfig} abstraction stays stable when it does.
 *
 * @param settings - Public server settings from the backend.
 * @returns The resolved application configuration.
 */
export function mapServerSettingsToAppConfig(settings: PublicServerSettings): AppConfig {
  return {
    features: {
      ...DEFAULT_APP_CONFIG.features,
      signUp: settings.signup_enabled,
    },
    branding: DEFAULT_APP_CONFIG.branding,
    map: {
      tileUrl: settings.tileserver_url,
      attribution: settings.tileserver_attribution,
    },
    enabledLocales: DEFAULT_APP_CONFIG.enabledLocales,
  }
}

/**
 * Fetches the instance's runtime configuration, derived from the public server
 * settings so per-instance flags have one source of truth.
 *
 * @returns The resolved {@link AppConfig}.
 * @throws {HttpError} When the public settings request fails.
 */
export async function fetchAppConfig(): Promise<AppConfig> {
  return mapServerSettingsToAppConfig(await fetchPublicServerSettings())
}
