import type { PublicServerSettings } from '@/features/config/types'

import { setAllowedRedirectSchemes } from '@/composables/useSafeRedirect'
import { apiFetch } from '@/services/http'

import { DEFAULT_MAP_CONFIG } from '../defaults'

/** Defaults used when public server settings cannot be reached. */
export const DEFAULT_PUBLIC_SERVER_SETTINGS: PublicServerSettings = {
  login_photo_set: false,
  signup_enabled: false,
  sso_enabled: false,
  local_login_enabled: true,
  sso_auto_redirect: false,
  units: 'metric',
  currency: 'euro',
  password_type: 'strict',
  password_length_regular_users: 8,
  password_length_admin_users: 12,
  num_records_per_page: 25,
  tileserver_url: DEFAULT_MAP_CONFIG.tileUrl,
  tileserver_attribution: DEFAULT_MAP_CONFIG.attribution,
  allowed_redirect_schemes: ['endurain'],
}

/**
 * Fetches public server settings needed by unauthenticated pages and applies the
 * server's allowed redirect schemes.
 *
 * @returns Public server settings.
 * @throws {HttpError} When the endpoint cannot be reached.
 */
export async function fetchPublicServerSettings(): Promise<PublicServerSettings> {
  const settings = await apiFetch<PublicServerSettings>('/public/server_settings', {
    auth: false,
    retryOnUnauthorized: false,
  })
  setAllowedRedirectSchemes(settings.allowed_redirect_schemes)
  return settings
}
