import type { Schemas } from '@/types'

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
 * @property weightUnits - Measurement system used to present body weight; falls
 *   back to `units` when the user has not set an explicit override.
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
  weightUnits: Schemas['Units']
  currency: Schemas['Currency']
  firstDayOfWeek: Schemas['WeekDay']
}

/**
 * Raw `/profile` response as returned by the backend. Narrowed from the
 * generated `UserMe` schema to the fields the app maps, so the snake-case
 * keys and number-encoded booleans track the backend contract exactly. Never
 * consume this shape in components — map it to {@link User} at the service
 * boundary.
 */
export type UserProfileDto = Pick<
  Schemas['UserMe'],
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
  | 'weight_units'
  | 'currency'
  | 'first_day_of_week'
>

/**
 * Answer of `POST /auth/login`, told apart by its `next_step`: `mfa` and `password_change` ask for one more step,
 * `tokens` and `exchange` end the sign-in. Derived from the generated schemas.
 */
export type LoginResponse =
  | Schemas['MFARequiredRead']
  | Schemas['PasswordChangeRequiredRead']
  | Schemas['MobileSessionRead']
  | Schemas['TokenWebRead']

/** Answer of `POST /auth/mfa/verify`: any login answer except another MFA step. */
export type MfaVerifyResponse = Exclude<LoginResponse, Schemas['MFARequiredRead']>

/** Answer of `POST /auth/password-change`: the web tokens, or the session of a mobile client. */
export type PasswordChangeResponse = Exclude<
  MfaVerifyResponse,
  Schemas['PasswordChangeRequiredRead']
>

/**
 * MFA verification request payload. Derived from the backend's generated
 * `MFALoginRequest` schema.
 */
export type MfaLoginRequest = Schemas['MFALoginRequest']

/**
 * Password-change step payload. Derived from the backend's generated
 * `PasswordChangeLoginRequest` schema.
 */
export type PasswordChangeLoginRequest = Schemas['PasswordChangeLoginRequest']

/**
 * Sign-up request payload sent to `POST /public/sign-up/request`. Derived from the
 * backend's generated `UserSignup` schema so a contract change surfaces as a
 * TypeScript error here instead of a silent runtime mismatch.
 */
export type SignUpRequest = Schemas['UserSignup']

/**
 * Sign-up response returned by the sign-up routes, naming what the client does next
 * (`next_step`: sign in, check the email, or await an administrator's approval).
 */
export type SignUpResponse = Schemas['SignUpRead']

/** Body of `POST /public/sign-up/confirm`: the emailed token and the chosen password. */
export type SignUpConfirm = Schemas['SignUpConfirm']

/** Body of `POST /public/email-change/confirm`: the token of the link emailed to the new address. */
export type EmailChangeConfirm = Schemas['EmailChangeConfirm']

/** Request body that reports an emailed email-change notice as not made by the account's owner. */
export type EmailChangeCancel = Schemas['EmailChangeCancel']

/** What `POST /public/email-change/cancel` did: whether the change had been confirmed and the address restored. */
export type EmailChangeCancelResult = Schemas['EmailChangeCancelRead']

/** Body of `POST /public/sign-up/resend`. */
export type SignUpResend = Schemas['SignUpResend']

/**
 * Whether the installation still needs its first administrator.
 *
 * @property onboardingRequired - `true` only while no account exists.
 */
export interface OnboardingStatus {
  onboardingRequired: boolean
}

/** Body of `POST /public/onboarding`, derived from the generated `OnboardingCreate` schema. */
export type OnboardingRequest = Schemas['OnboardingCreate']

/** Sign-out answer: the identity provider's end-session URL, or `null` when there is none. */
export type LogoutResponse = Schemas['LogoutRead']
