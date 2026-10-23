import type { ServerSettingsFormValues } from '@/features/serverSettings/types'

/** The tabs of the server settings page, in display order. */
export const SETTINGS_TABS = ['general', 'access', 'maps', 'email', 'logs'] as const

/** One tab of the server settings page. */
export type SettingsTab = (typeof SETTINGS_TABS)[number]

/** The tab shown when the URL names none, or an unknown one. */
export const DEFAULT_SETTINGS_TAB: SettingsTab = 'general'

/**
 * Narrows a raw `?tab=` query value to a known tab.
 *
 * @param value - The raw query value.
 * @returns The tab, or the default tab when the value names none.
 */
export function parseSettingsTab(value: unknown): SettingsTab {
  return SETTINGS_TABS.find((tab) => tab === value) ?? DEFAULT_SETTINGS_TAB
}

/**
 * The tab each editable field lives on. Typed over every form field so adding
 * a field without placing it is a compile error; drives the unsaved-changes dots.
 */
export const FIELD_TABS: Record<keyof ServerSettingsFormValues, SettingsTab> = {
  units: 'general',
  currency: 'general',
  numRecordsPerPage: 'general',
  readNotificationRetentionDays: 'general',
  signupEnabled: 'access',
  signupRequireAdminApproval: 'access',
  signupRequireEmailVerification: 'access',
  ssoEnabled: 'access',
  localLoginEnabled: 'access',
  ssoAutoRedirect: 'access',
  passwordType: 'access',
  passwordLengthRegularUsers: 'access',
  passwordLengthAdminUsers: 'access',
  sessionIdleTimeoutEnabled: 'access',
  sessionIdleTimeoutHours: 'access',
  sessionAbsoluteTimeoutHours: 'access',
  accessTokenExpireMinutes: 'access',
  refreshTokenExpireDays: 'access',
  publicShareableLinks: 'access',
  publicShareableLinksUserInfo: 'access',
  tileserverUrl: 'maps',
  tileserverAttribution: 'maps',
  tileserverApiKey: 'maps',
  removeTileserverApiKey: 'maps',
  tileserverRegenerateThumbnailsOnChange: 'maps',
  mapBackgroundColor: 'maps',
  geocodingService: 'maps',
  geocodingHost: 'maps',
  geocodingUseHttps: 'maps',
  geocodingRateLimit: 'maps',
  geocodingApiKey: 'maps',
  removeGeocodingApiKey: 'maps',
}
