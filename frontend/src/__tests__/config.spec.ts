import { describe, expect, it, vi } from 'vitest'

import type { PublicServerSettings } from '@/features/config/types'

import { DEFAULT_MAP_CONFIG } from '@/features/config/defaults'
import {
  DEFAULT_APP_CONFIG,
  fetchAppConfig,
  mapServerSettingsToAppConfig,
} from '@/features/config/services/config'
import {
  DEFAULT_PUBLIC_SERVER_SETTINGS,
  fetchPublicServerSettings,
} from '@/features/config/services/serverSettings'

vi.mock('@/features/config/services/serverSettings', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('@/features/config/services/serverSettings')>()
  return {
    ...original,
    fetchPublicServerSettings: vi.fn<typeof original.fetchPublicServerSettings>(),
  }
})

const publicSettings: PublicServerSettings = {
  login_photo_set: false,
  signup_enabled: true,
  sso_enabled: false,
  local_login_enabled: true,
  sso_auto_redirect: false,
  units: 'metric',
  currency: 'euro',
  password_type: 'strict',
  password_length_regular_users: 8,
  password_length_admin_users: 12,
  num_records_per_page: 25,
  tileserver_url: 'https://tiles.test/{z}/{x}/{y}.png',
  tileserver_attribution: '&copy; Test tiles',
}

describe('default map configuration', () => {
  it('is shared by app and public server fallbacks', () => {
    expect(DEFAULT_APP_CONFIG.map).toBe(DEFAULT_MAP_CONFIG)
    expect(DEFAULT_PUBLIC_SERVER_SETTINGS.tileserver_url).toBe(DEFAULT_MAP_CONFIG.tileUrl)
    expect(DEFAULT_PUBLIC_SERVER_SETTINGS.tileserver_attribution).toBe(
      DEFAULT_MAP_CONFIG.attribution,
    )
  })
})

describe('mapServerSettingsToAppConfig', () => {
  it('maps the signUp feature flag from the server signup flag', () => {
    expect(
      mapServerSettingsToAppConfig({ ...publicSettings, signup_enabled: false }).features.signUp,
    ).toBe(false)
    expect(
      mapServerSettingsToAppConfig({ ...publicSettings, signup_enabled: true }).features.signUp,
    ).toBe(true)
  })

  it('keeps self-hosted defaults for fields the public settings do not carry', () => {
    const config = mapServerSettingsToAppConfig(publicSettings)

    expect(config.features.strava).toBe(DEFAULT_APP_CONFIG.features.strava)
    expect(config.features.garmin).toBe(DEFAULT_APP_CONFIG.features.garmin)
    expect(config.features.federation).toBe(DEFAULT_APP_CONFIG.features.federation)
    expect(config.branding).toEqual(DEFAULT_APP_CONFIG.branding)
    expect(config.map).toEqual({
      tileUrl: publicSettings.tileserver_url,
      attribution: publicSettings.tileserver_attribution,
    })
    expect(config.enabledLocales).toBe(DEFAULT_APP_CONFIG.enabledLocales)
  })
})

describe('fetchAppConfig', () => {
  it('derives the app config from the public server settings', async () => {
    vi.mocked(fetchPublicServerSettings).mockResolvedValue({
      ...publicSettings,
      signup_enabled: false,
    })

    const config = await fetchAppConfig()

    expect(fetchPublicServerSettings).toHaveBeenCalledOnce()
    expect(config.features.signUp).toBe(false)
  })
})
