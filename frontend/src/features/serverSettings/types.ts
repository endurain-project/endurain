import type { Schemas } from '@/types'

/** Raw authenticated server-settings payload (snake_case wire shape). */
export type ServerSettingsDto = Schemas['ServerSettingsRead']

/**
 * Editable server-settings body for the `PUT`. The backend forbids extra
 * fields and replaces the whole record, so every column must round-trip — the
 * derived type makes a missing field a compile error in {@link toServerSettingsWire}.
 */
export type ServerSettingsEditDto = Schemas['ServerSettingsEdit']

/** Raw tile-map template payload (snake_case wire shape). */
export type TileMapsTemplateDto = Schemas['TileMapsTemplate']

/** Measurement system, mirrored from the backend enum (`metric` | `imperial`). */
export type Units = Schemas['Units']

/** Currency, mirrored from the backend enum (`euro` | `dollar` | `pound`). */
export type Currency = Schemas['Currency']

/** Password policy level, mirrored from the backend enum (`strict` | `length_only`). */
export type PasswordType = Schemas['PasswordType']

/**
 * The clean, camel-cased server-settings model used across the admin zone.
 * Carries every editable column — not just the ones a section renders —
 * because the backend's edit endpoint replaces the whole record, so unedited
 * fields must round-trip untouched (see {@link toServerSettingsWire}). Mapped
 * from {@link ServerSettingsDto} at the service boundary so components never
 * touch the raw DTO.
 *
 * @property id - Stable singleton identifier (always 1; round-tripped).
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
 * @property tileserverApiKey - Tile-server API key (stored encrypted), or `null`.
 * @property tileserverRegenerateThumbnailsOnChange - Whether to regenerate thumbnails when map settings change.
 * @property mapBackgroundColor - Map background colour (`#RRGGBB`).
 * @property passwordType - Password policy enforcement level.
 * @property passwordLengthRegularUsers - Minimum password length for regular users.
 * @property passwordLengthAdminUsers - Minimum password length for admin users.
 */
export interface ServerSettings {
  id: number
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
  tileserverApiKey: string | null
  tileserverRegenerateThumbnailsOnChange: boolean
  mapBackgroundColor: string
  passwordType: PasswordType
  passwordLengthRegularUsers: number
  passwordLengthAdminUsers: number
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
 * The form-editable subset of {@link ServerSettings}. Excludes `id` (constant)
 * and `loginPhotoSet` (managed by the separate upload/delete actions), both of
 * which round-trip from the freshest server state at save time.
 */
export type ServerSettingsFormValues = Omit<ServerSettings, 'id' | 'loginPhotoSet'>

/** Raw email-status payload (the SMTP settings are valid, or why they are not). */
export type EmailStatusDto = Schemas['EmailStatus']
