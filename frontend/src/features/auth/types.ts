import type { AuthTokenResponse, Schemas } from '@/types'

/**
 * The authenticated user as consumed by the app: a clean, camel-cased, fully
 * typed model decoupled from the backend wire format, so API changes are
 * absorbed by the mapper instead of scattered across components.
 *
 * @property id - Stable unique identifier.
 * @property name - Display name shown in the navbar.
 * @property username - Login handle.
 * @property email - Account email.
 * @property preferredLanguage - Backend language code used to pick a locale.
 * @property accessType - Authorization tier.
 * @property active - Whether the account is active.
 * @property mfaEnabled - Whether MFA is enabled.
 * @property avatarUrl - Absolute avatar URL, or `null` when unset.
 * @property isStravaLinked - Whether a Strava integration is linked.
 * @property isGarminConnectLinked - Whether a Garmin Connect integration is linked.
 * @property hasLocalPassword - Whether the account has a local password.
 * @property units - Measurement system used to present distances and heights.
 * @property currency - Preferred currency for monetary values.
 * @property firstDayOfWeek - First day used for calendar week boundaries.
 */
export interface User {
  id: number
  name: string
  username: string
  email: string
  preferredLanguage: string
  accessType: string
  active: boolean
  mfaEnabled: boolean
  avatarUrl: string | null
  isStravaLinked: boolean
  isGarminConnectLinked: boolean
  hasLocalPassword: boolean
  units: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
}

/**
 * Raw `/profile` response as returned by the backend. Narrowed from the
 * generated `UsersMe` schema to the fields the app maps, so the snake-case
 * keys and number-encoded booleans track the backend contract exactly. Never
 * consume this shape in components — map it to {@link User} at the service
 * boundary.
 */
export type UserProfileDto = Pick<
  Schemas['UsersMe'],
  | 'id'
  | 'name'
  | 'username'
  | 'email'
  | 'preferred_language'
  | 'access_type'
  | 'active'
  | 'mfa_enabled'
  | 'photo_path'
  | 'is_strava_linked'
  | 'is_garminconnect_linked'
  | 'has_local_password'
  | 'units'
  | 'currency'
  | 'first_day_of_week'
>

/**
 * Backend response indicating that MFA is required before login completes.
 * Derived from the generated `MFARequiredResponse` schema, with
 * `mfa_required` narrowed to the literal `true` so it acts as the discriminant
 * of the {@link LoginResponse} union.
 */
export type MfaRequiredResponse = Omit<Schemas['MFARequiredResponse'], 'mfa_required'> & {
  mfa_required: true
}

/** Login response from the backend. */
export type LoginResponse = AuthTokenResponse | MfaRequiredResponse

/**
 * MFA verification request payload. Derived from the backend's generated
 * `MFALoginRequest` schema.
 */
export type MfaLoginRequest = Schemas['MFALoginRequest']

/**
 * Logout response from the backend. Derived from the generated `LogoutResponse`
 * schema so a contract change surfaces as a TypeScript error here instead of a
 * silent runtime mismatch.
 */
export type LogoutResponse = Schemas['LogoutResponse']

/**
 * Sign-up request payload sent to `POST /sign-up/request`. Derived from the
 * backend's generated `UsersSignup` schema so a contract change surfaces as a
 * TypeScript error here instead of a silent runtime mismatch.
 */
export type SignUpRequest = Schemas['UsersSignup']

/**
 * Sign-up response returned by `POST /sign-up/request`, indicating whether the
 * account still needs email verification and/or admin approval before login.
 */
export type SignUpResponse = Schemas['SignUpResponse']
