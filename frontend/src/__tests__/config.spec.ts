import { describe, expect, it } from 'vitest'

import type { PublicServerSettings } from '@/features/config/types'

import { DEFAULT_MAP_CONFIG } from '@/features/config/defaults'
import { DEFAULT_APP_CONFIG, mapServerSettingsToAppConfig } from '@/features/config/services/config'
import { DEFAULT_PUBLIC_SERVER_SETTINGS } from '@/features/config/services/serverSettings'

const publicSettings: PublicServerSettings = {
  login_photo_set: false,
  signup_enabled: true,
  signup_require_email_verification: false,
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
  allowed_redirect_schemes: ['endurain'],
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

describe('public server settings fallback', () => {
  it('carries the sign-up email verification flag, off when the server is unreachable', () => {
    expect(DEFAULT_PUBLIC_SERVER_SETTINGS.signup_require_email_verification).toBe(false)
  })
})
