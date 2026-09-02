import type { PublicServerSettings } from '@/features/config/types'

import { apiFetch } from '@/services/http'

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
  tileserver_url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  tileserver_attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}

/**
 * Fetches public server settings needed by unauthenticated pages.
 *
 * @returns Public server settings.
 * @throws {HttpError} When the endpoint cannot be reached.
 */
export function fetchPublicServerSettings(): Promise<PublicServerSettings> {
  return apiFetch<PublicServerSettings>('/public/server_settings', {
    auth: false,
    retryOnUnauthorized: false,
  })
}
