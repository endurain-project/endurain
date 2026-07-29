import type { Schemas } from '@/types'

/** Raw `UsersRead` payload as returned by the backend (snake_case wire shape). */
export type UserDto = Schemas['UsersRead']

/** Raw paginated users list payload. */
export type UsersListResponseDto = Schemas['UsersListResponse']

/** User access tier, mirrored from the backend enum (`regular` | `admin`). */
export type UserAccessType = Schemas['UserAccessType']

/**
 * The clean, camel-cased user model used across the admin users zone. Carries
 * every `UsersRead` field — not just the ones shown — because the backend's
 * edit endpoint replaces the whole record, so unedited fields must round-trip
 * untouched (see `toUserWire`). Mapped from {@link UserDto} at the service
 * boundary so components never touch the raw DTO.
 *
 * @property id - Stable unique identifier.
 * @property name - Full display name.
 * @property username - Login handle.
 * @property email - Account email.
 * @property accessType - Authorization tier.
 * @property active - Whether the account is enabled.
 * @property emailVerified - Whether the email has been verified.
 * @property pendingAdminApproval - Whether the sign-up awaits admin approval.
 * @property mfaEnabled - Whether MFA is enabled.
 * @property externalAuthCount - Number of linked external identity providers.
 * @property preferredLanguage - Backend language code.
 * @property gender - Gender.
 * @property units - Measurement system.
 * @property currency - Preferred currency.
 * @property firstDayOfWeek - First day of the week.
 * @property city - City, or `null`.
 * @property birthdate - Birthdate (ISO string), or `null`.
 * @property height - Height in centimetres, or `null`.
 * @property maxHeartRate - Max heart rate in bpm, or `null`.
 * @property photoPath - Backend-issued photo URL, or `null` when unset.
 * @property avatarUrl - Servable avatar URL derived from `photoPath`, or `null`.
 */
export interface ManagedUser {
  id: number
  name: string
  username: string
  email: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  pendingAdminApproval: boolean
  mfaEnabled: boolean
  externalAuthCount: number
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string | null
  birthdate: string | null
  height: number | null
  maxHeartRate: number | null
  photoPath: string | null
  avatarUrl: string | null
}

/** One page of the paginated users list. */
export interface UsersPage {
  records: ManagedUser[]
  total: number
}

/**
 * A user's public-facing profile, shown on the `/user/:id` page and in
 * follower/following lists. A deliberately privacy-conscious subset of
 * `UsersRead` — only the fields a profile renders, omitting email, birthdate,
 * and other sensitive columns. Mapped from {@link UserDto} at the service
 * boundary so components never touch the raw DTO.
 *
 * @property id - Stable unique identifier.
 * @property name - Full display name.
 * @property username - Login handle, shown as `@username`.
 * @property city - City, or `null` when unset.
 * @property avatarUrl - Servable avatar URL derived from the photo path, or `null`.
 */
export interface PublicUser {
  id: number
  name: string
  username: string
  city: string | null
  avatarUrl: string | null
}

/**
 * The five admin user-list filters. Each flag, when `true`, includes that
 * category in the results; setting it to `false` excludes the category
 * server-side (mirrors v1's filter set).
 *
 * @property showInactive - Include deactivated accounts.
 * @property showEmailUnverified - Include accounts with an unverified email.
 * @property showPendingApproval - Include sign-ups awaiting admin approval.
 * @property showExternalAuth - Include accounts linked to an external IdP.
 * @property showLocalAuth - Include local (password) accounts.
 */
export interface UserFilters {
  showInactive: boolean
  showEmailUnverified: boolean
  showPendingApproval: boolean
  showExternalAuth: boolean
  showLocalAuth: boolean
}

/** Pagination + filter input for a users list request. */
export interface UsersListParams extends UserFilters {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
}

/**
 * The full set of user fields the admin form can edit, mirroring v1's add/edit
 * modal. Sent merged onto {@link ManagedUser} so the rest of the record (id,
 * mfa, external auth count, photo) round-trips untouched (see `toUserWire`).
 */
export interface EditUserFields {
  name: string
  username: string
  email: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  pendingAdminApproval: boolean
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string | null
  birthdate: string | null
  height: number | null
  maxHeartRate: number | null
}

/**
 * Fields the admin supplies to create a user — the same set as
 * {@link EditUserFields} plus the initial password.
 */
export interface CreateUserInput {
  name: string
  username: string
  email: string
  password: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  pendingAdminApproval: boolean
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string | null
  birthdate: string | null
  height: number | null
  maxHeartRate: number | null
}

/** Raw `UsersSessionsRead` payload as returned by the backend (snake_case). */
export type UserSessionDto = Schemas['UsersSessionsRead']

/**
 * A user session in the admin view, camel-cased from {@link UserSessionDto}.
 *
 * @property id - Stable session identifier.
 * @property ipAddress - Client IP address.
 * @property deviceType - Device category (e.g. desktop, mobile).
 * @property operatingSystem - Operating system name.
 * @property operatingSystemVersion - Operating system version.
 * @property browser - Browser name.
 * @property browserVersion - Browser version.
 * @property createdAt - Session creation timestamp (ISO string).
 * @property lastActivityAt - Last activity timestamp (ISO string).
 * @property expiresAt - Expiry timestamp (ISO string).
 */
export interface UserSession {
  id: string
  ipAddress: string
  deviceType: string
  operatingSystem: string
  operatingSystemVersion: string
  browser: string
  browserVersion: string
  createdAt: string
  lastActivityAt: string
  expiresAt: string
}

/** Raw `UsersIdentityProviderResponse` payload as returned by the backend. */
export type UserIdentityProviderDto = Schemas['UsersIdentityProviderResponse']

/**
 * A user's linked identity provider in the admin view, camel-cased from
 * {@link UserIdentityProviderDto}.
 *
 * @property id - Link id (stable list key).
 * @property idpId - Identity provider id (used to unlink).
 * @property name - Provider display name (may be null).
 * @property slug - Provider slug (may be null).
 * @property providerType - Provider type, e.g. `oidc` (may be null).
 * @property subject - Account subject/id at the provider.
 * @property linkedAt - When the link was created (ISO string).
 * @property lastLogin - Last login using this provider (ISO string), if any.
 */
export interface UserIdentityProvider {
  id: number
  idpId: number
  name: string | null
  slug: string | null
  providerType: string | null
  subject: string
  linkedAt: string
  lastLogin: string | null
}
