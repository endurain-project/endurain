import type { Schemas } from '@/types'

/** Raw `UserRead` payload as returned by the backend (snake_case wire shape). */
export type UserDto = Schemas['UserRead']

/** `UserAdminEdit` payload: the body of an administrative edit of a user. */
export type UserEditDto = Schemas['UserAdminEdit']

/** Raw `UserPublicRead` payload: what any signed-in or anonymous viewer may learn about a user. */
export type PublicUserDto = Schemas['UserPublicRead']

/** Where a user's queued account deletion is, as the backend reports it. */
export type UserDeletionStatus = Schemas['UserDeletionStatus']

/** Raw paginated users list payload. */
export type UsersListResponseDto = Schemas['Page_UserRead_']

/** User access tier, mirrored from the backend enum (`regular` | `admin`). */
export type UserAccessType = Schemas['UserAccessType']

/**
 * The clean, camel-cased user model used across the admin users zone. Carries
 * every `UserRead` field, not just the ones shown, so an edit can be compared
 * with the stored record and send only what changed (see `updateUser`). Mapped from {@link UserDto} at the service
 * boundary so components never touch the raw DTO.
 *
 * @property id - Stable unique identifier.
 * @property name - Full display name.
 * @property username - Login handle.
 * @property email - Account email.
 * @property accessType - Authorization tier.
 * @property active - Whether the account is enabled.
 * @property emailVerified - Whether the email has been verified.
 * @property pendingEmail - Address awaiting confirmation, or `null` when no change is pending.
 * @property pendingEmailExpiresAt - When the pending address's confirmation link expires, or `null`.
 * @property deletionRequestedAt - When the account was queued for deletion, or `null` when it is not being deleted.
 * @property pendingAdminApproval - Whether the sign-up awaits admin approval.
 * @property mfaEnabled - Whether MFA is enabled.
 * @property externalAuthCount - Number of linked external identity providers.
 * @property preferredLanguage - Backend language code.
 * @property gender - Gender.
 * @property units - Measurement system.
 * @property weightUnits - Weight units override, or `null` to follow `units`.
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
  /** The row version, sent back in `If-Match` so an edit of a stale copy is refused. */
  version: number
  name: string
  username: string
  email: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  pendingEmail: string | null
  pendingEmailExpiresAt: string | null
  deletionRequestedAt: string | null
  pendingAdminApproval: boolean
  mfaEnabled: boolean
  externalAuthCount: number
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  weightUnits: Schemas['Units'] | null
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
 * `UserRead` — only the fields a profile renders, omitting email, birthdate,
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
 * Public profile data and the summary metrics shown above the profile tabs.
 *
 * @property user - The profile's public user projection.
 * @property weekStats - Visible per-sport activity totals for the current week.
 * @property monthStats - Visible per-sport activity totals for the current month.
 * @property monthActivityCount - Visible activity count for the current month.
 * @property followersCount - Accepted followers, or null when the network is private.
 * @property followingCount - Accepted followees, or null when the network is private.
 */
export interface UserProfileOverview {
  user: PublicUser
  weekStats: Schemas['ActivityStatsRead']
  monthStats: Schemas['ActivityStatsRead']
  monthActivityCount: number
  followersCount: number | null
  followingCount: number | null
}

/**
 * The five admin user-list filters. Each flag, when `true`, includes that
 * category in the results; setting it to `false` excludes the category
 * server-side (`active=true`, `email_verified=true`, `pending_approval=false`,
 * `external_auth=true` or `false` when exactly one of the two authentication switches is off).
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
  /** Keep only users whose username contains this text (at least 3 characters). */
  username?: string
}

/**
 * The full set of user fields the admin form can edit, mirroring v1's add/edit
 * modal. Merged onto {@link ManagedUser}, and only the values that differ from
 * the stored ones are sent (see `updateUser`).
 */
export interface EditUserFields {
  name: string
  username: string
  email: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  weightUnits: Schemas['Units'] | null
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string | null
  birthdate: string | null
  height: number | null
  maxHeartRate: number | null
}

/**
 * Fields the admin supplies to create a user — the same set as
 * {@link EditUserFields} plus the initial password, which is left out to invite the user to choose one.
 */
export interface CreateUserInput {
  name: string
  username: string
  email: string
  password?: string
  accessType: UserAccessType
  active: boolean
  emailVerified: boolean
  preferredLanguage: Schemas['Language']
  gender: Schemas['Gender']
  units: Schemas['Units']
  weightUnits: Schemas['Units'] | null
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
  city: string | null
  birthdate: string | null
  height: number | null
  maxHeartRate: number | null
}

/** Raw `UserSessionsRead` payload as returned by the backend (snake_case). */
export type UserSessionDto = Schemas['UserSessionsRead']

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
 * @property appRedirectUri - Redirect address of the native app the session was signed in through, or null.
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
  appRedirectUri: string | null
}

/** Raw `IdentityProviderLinkRead` payload as returned by the backend. */
export type UserIdentityProviderDto = Schemas['IdentityProviderLinkRead']

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
  id: string
  idpId: number
  name: string | null
  slug: string | null
  providerType: string | null
  subject: string
  linkedAt: string
  lastLogin: string | null
}
