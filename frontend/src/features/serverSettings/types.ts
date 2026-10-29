import type { Schemas } from '@/types'

/** Raw authenticated server-settings payload (snake_case wire shape). */
export type ServerSettingsDto = Schemas['ServerSettingsAdminRead']

/**
 * Editable server-settings body for the `PUT`. The backend forbids extra
 * fields and replaces the whole record, so every column must round-trip — the
 * derived type makes a missing field a compile error in {@link toServerSettingsWire}.
 */
export type ServerSettingsEditDto = Schemas['ServerSettingsEdit']

/** Whether the server-log viewer is available on this deployment. */
export type LogsStatusDto = Schemas['LogsStatus']

/** One record of the server log. */
export type LogEntry = Schemas['LogEntry']

/** A slice of the server log with the cursor for reading what follows it. */
export type LogPage = Schemas['LogPage']

/** Log severity, mirrored from the backend enum (`DEBUG` to `CRITICAL`). */
export type LogLevel = Schemas['LogLevel']

/**
 * What the log viewer filters on.
 *
 * @property level - Lowest severity to show, or null for all.
 * @property search - Text a record must contain; empty for no text filter.
 */
export interface LogFilters {
  level: LogLevel | null
  search: string
}

/** Raw tile-map template payload (snake_case wire shape). */
export type TileMapsTemplateDto = Schemas['TileMapsTemplate']

/** Measurement system, mirrored from the backend enum (`metric` | `imperial`). */
export type Units = Schemas['Units']

/** Currency, mirrored from the backend enum (`euro` | `dollar` | `pound`). */
export type Currency = Schemas['Currency']

/** Password policy level, mirrored from the backend enum (`strict` | `length_only`). */
export type PasswordType = Schemas['PasswordType']

/** Reverse-geocoding service, mirrored from the backend enum (`nominatim` | `photon` | `geocode`). */
export type GeocodingService = Schemas['GeocodingService']

/**
 * The clean, camel-cased server-settings model used across the admin zone.
 * Carries every editable column — not just the ones a section renders —
 * because the backend's edit endpoint replaces the whole record, so unedited
 * fields must round-trip untouched (see {@link toServerSettingsWire}). Mapped
 * from {@link ServerSettingsDto} at the service boundary so components never
 * touch the raw DTO.
 *
 * @property id - Stable singleton identifier (always 1; round-tripped).
 * @property version - Row version behind the `ETag`, echoed as `If-Match` on save so a stale form is refused.
 * @property units - Default measurement system for new users.
 * @property currency - Default currency for new users.
 * @property numRecordsPerPage - Server-enforced page size for paginated lists.
 * @property publicShareableLinks - Whether public shareable activity links are enabled.
 * @property publicShareableLinksUserInfo - Whether public links reveal the owner's info.
 * @property loginPhotoSet - Whether a custom login photo is configured (managed via upload/delete).
 * @property signupEnabled - Whether self-service sign-up is allowed.
 * @property signupRequireAdminApproval - Whether new sign-ups await admin approval.
 * @property signupRequireEmailVerification - Whether new sign-ups must verify email.
 * @property ssoEnabled - Whether SSO/IdP login is enabled.
 * @property localLoginEnabled - Whether username/password login is allowed.
 * @property ssoAutoRedirect - Whether to auto-redirect when a single IdP is configured.
 * @property tileserverUrl - Map tile URL template (`{z}`/`{x}`/`{y}` placeholders).
 * @property tileserverAttribution - Attribution string shown on the map.
 * @property tileserverApiKeySet - Whether a tile-server API key is stored (the key itself is never returned).
 * @property tileserverRegenerateThumbnailsOnChange - Whether to regenerate thumbnails when map settings change.
 * @property mapBackgroundColor - Map background colour (`#RRGGBB`).
 * @property passwordType - Password policy enforcement level.
 * @property passwordLengthRegularUsers - Minimum password length for regular users.
 * @property passwordLengthAdminUsers - Minimum password length for admin users.
 * @property geocodingService - Reverse-geocoding service.
 * @property geocodingHost - Host (and optional port) of the geocoding service, or null for its default host.
 * @property geocodingUseHttps - Whether the geocoding host is addressed over HTTPS.
 * @property geocodingRateLimit - Maximum geocoding requests per second (0 disables throttling).
 * @property sessionIdleTimeoutEnabled - Whether the session idle and absolute timeouts are enforced.
 * @property sessionIdleTimeoutHours - Hours of inactivity that end a session.
 * @property sessionAbsoluteTimeoutHours - Hours after which a session ends whatever its activity.
 * @property accessTokenExpireMinutes - Access token lifetime in minutes.
 * @property refreshTokenExpireDays - Refresh token lifetime in days.
 * @property readNotificationRetentionDays - Days after which read notifications are purged (0 keeps them forever).
 * @property geocodingApiKeySet - Whether a geocoding API key is stored (the key itself is never returned).
 * @property envManaged - Field name (snake_case) to the environment variable that sets it; those fields are read-only.
 */
export interface ServerSettings {
  id: number
  version: number
  units: Units
  currency: Currency
  numRecordsPerPage: number
  publicShareableLinks: boolean
  publicShareableLinksUserInfo: boolean
  loginPhotoSet: boolean
  signupEnabled: boolean
  signupRequireAdminApproval: boolean
  signupRequireEmailVerification: boolean
  ssoEnabled: boolean
  localLoginEnabled: boolean
  ssoAutoRedirect: boolean
  tileserverUrl: string
  tileserverAttribution: string
  tileserverApiKeySet: boolean
  tileserverRegenerateThumbnailsOnChange: boolean
  mapBackgroundColor: string
  passwordType: PasswordType
  passwordLengthRegularUsers: number
  passwordLengthAdminUsers: number
  geocodingService: GeocodingService
  geocodingHost: string | null
  geocodingUseHttps: boolean
  geocodingRateLimit: number
  sessionIdleTimeoutEnabled: boolean
  sessionIdleTimeoutHours: number
  sessionAbsoluteTimeoutHours: number
  accessTokenExpireMinutes: number
  refreshTokenExpireDays: number
  readNotificationRetentionDays: number
  geocodingApiKeySet: boolean
  envManaged: Record<string, string>
}

/**
 * A selectable tile-server preset offered in the maps section. Selecting one
 * fills the URL/attribution/background-colour fields; `requiresApiKey*` drive
 * the inline guidance about where an API key must be configured.
 *
 * @property templateId - Stable preset identifier (or the sentinel `custom`).
 * @property name - Human-readable preset name.
 * @property urlTemplate - Tile URL template the preset applies.
 * @property attribution - Attribution string the preset applies.
 * @property mapBackgroundColor - Background colour the preset applies.
 * @property requiresApiKeyFrontend - Whether the preset needs a frontend API key.
 * @property requiresApiKeyBackend - Whether the preset needs a backend API key.
 */
export interface TileMapsTemplate {
  templateId: string
  name: string
  urlTemplate: string
  attribution: string
  mapBackgroundColor: string
  requiresApiKeyFrontend: boolean
  requiresApiKeyBackend: boolean
}

/**
 * The form-editable subset of {@link ServerSettings}. Excludes `id` (constant),
 * `version` and `loginPhotoSet` (managed by the separate upload/delete actions), both of
 * which round-trip from the freshest server state at save time. The API keys
 * are write-only: `tileserverApiKey` / `geocodingApiKey` hold a newly typed key
 * (empty keeps the stored one) and `removeTileserverApiKey` /
 * `removeGeocodingApiKey` ask for the stored key to be removed. The geocoding host,
 * rate limit and the session policy and retention numbers are strings because the text inputs bind
 * strings; they are converted on save.
 */
export type ServerSettingsFormValues = Omit<
  ServerSettings,
  | 'id'
  | 'version'
  | 'loginPhotoSet'
  | 'tileserverApiKeySet'
  | 'geocodingApiKeySet'
  | 'envManaged'
  | 'geocodingHost'
  | 'geocodingRateLimit'
  | 'sessionIdleTimeoutHours'
  | 'sessionAbsoluteTimeoutHours'
  | 'accessTokenExpireMinutes'
  | 'refreshTokenExpireDays'
  | 'readNotificationRetentionDays'
> & {
  tileserverApiKey: string
  removeTileserverApiKey: boolean
  geocodingHost: string
  geocodingRateLimit: string
  geocodingApiKey: string
  removeGeocodingApiKey: boolean
  sessionIdleTimeoutHours: string
  sessionAbsoluteTimeoutHours: string
  accessTokenExpireMinutes: string
  refreshTokenExpireDays: string
  readNotificationRetentionDays: string
}

/**
 * Server settings to persist. The API keys are write-only: `undefined` keeps the
 * stored key, `null` removes it, a string replaces it.
 */
export type ServerSettingsUpdate = Omit<
  ServerSettings,
  'tileserverApiKeySet' | 'geocodingApiKeySet' | 'envManaged'
> & {
  tileserverApiKey?: string | null
  geocodingApiKey?: string | null
}

/** The login photo after an upload: the version that identifies the stored image. */
export type LoginPhotoDto = Schemas['LoginPhotoRead']

/** Raw email-status payload (the mail settings are valid, or why they are not). */
export type EmailStatusDto = Schemas['EmailStatus']

/** Raw authenticated mail-settings payload (snake_case wire shape). */
export type MailSettingsDto = Schemas['MailSettingsAdminRead']

/** Editable mail-settings body for the `PUT`; the backend replaces the whole record. */
export type MailSettingsEditDto = Schemas['MailSettingsEdit']

/** Mail connection security, mirrored from the backend enum (`starttls` | `ssl` | `none`). */
export type MailSecurity = Schemas['MailSecurity']

/**
 * The clean, camel-cased mail-server settings. Mapped from {@link MailSettingsDto}
 * at the service boundary so components never touch the raw DTO.
 *
 * @property version - Row version behind the `ETag`, echoed as `If-Match` on save so a stale form is refused.
 * @property host - Mail server hostname, or null when mail is disabled.
 * @property port - Mail server port.
 * @property security - How the connection is secured.
 * @property username - Authentication username, or null.
 * @property fromAddress - Sender address, or null when the username is used.
 * @property passwordSet - Whether a password is stored (the password itself is never returned).
 * @property envManaged - Field name to the environment variable that sets it; those fields are read-only.
 */
export interface MailSettings {
  version: number
  host: string | null
  port: number
  security: MailSecurity
  username: string | null
  fromAddress: string | null
  passwordSet: boolean
  envManaged: Record<string, string>
}

/**
 * The form-editable subset of {@link MailSettings}. The password is write-only:
 * `password` holds a newly typed one (empty keeps the stored one) and
 * `removePassword` asks for the stored one to be removed. The port is a string
 * because the text input binds strings; it is validated and converted on save.
 */
export interface MailSettingsFormValues {
  host: string
  port: string
  security: MailSecurity
  username: string
  fromAddress: string
  password: string
  removePassword: boolean
}

/**
 * Mail settings to persist. `password` is write-only: `undefined` keeps the
 * stored password, `null` removes it, a string replaces it.
 */
export type MailSettingsUpdate = Omit<MailSettings, 'passwordSet' | 'envManaged'> & {
  password?: string | null
}
