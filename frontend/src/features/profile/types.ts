import type { Schemas } from '@/types'

/** Raw authenticated `/profile` payload (snake_case wire shape). */
export type ProfileDto = Schemas['UsersMe']

/** Edit body for the user's own profile (all fields optional). */
export type ProfileUpdateDto = Schemas['ProfileUpdate']

/** Update body for the user's privacy settings. */
export type PrivacyUpdateDto = Schemas['UsersPrivacySettingsUpdate']

/** Activity visibility level, mirrored from the backend enum. */
export type ActivityVisibility = Schemas['ActivityVisibility']

/**
 * Per-activity-field privacy preferences. Each `hide*` flag, when on, omits
 * that data from activities shared beyond the owner. Mapped from the backend's
 * nullable `hide_activity_*` columns (normalized to plain booleans).
 *
 * @property defaultActivityVisibility - Visibility applied to new activities.
 * @property hideStartTime - Hide the activity start time.
 * @property hideLocation - Hide the activity location.
 * @property hideMap - Hide the activity map/route.
 * @property hideHr - Hide heart-rate data.
 * @property hidePower - Hide power data.
 * @property hideCadence - Hide cadence data.
 * @property hideElevation - Hide elevation data.
 * @property hideSpeed - Hide speed data.
 * @property hidePace - Hide pace data.
 * @property hideLaps - Hide lap splits.
 * @property hideWorkoutSetsSteps - Hide workout sets and steps.
 * @property hideGear - Hide the gear used.
 */
export interface PrivacySettings {
  defaultActivityVisibility: ActivityVisibility
  hideStartTime: boolean
  hideLocation: boolean
  hideMap: boolean
  hideHr: boolean
  hidePower: boolean
  hideCadence: boolean
  hideElevation: boolean
  hideSpeed: boolean
  hidePace: boolean
  hideLaps: boolean
  hideWorkoutSetsSteps: boolean
  hideGear: boolean
}

/**
 * The clean, camel-cased self-profile model used by the profile settings zone.
 * Carries the editable identity fields plus the read-only account context and
 * the nested {@link PrivacySettings}. Mapped from {@link ProfileDto} at the
 * service boundary so components never touch the raw DTO.
 *
 * @property id - Stable unique identifier.
 * @property name - Display name.
 * @property username - Login handle.
 * @property email - Account email.
 * @property city - City, or `null`.
 * @property birthdate - Birthdate (ISO date), or `null`.
 * @property gender - Gender.
 * @property units - Measurement system.
 * @property currency - Preferred currency.
 * @property height - Height in centimetres, or `null`.
 * @property maxHeartRate - Max heart rate in bpm, or `null`.
 * @property preferredLanguage - Backend language code.
 * @property firstDayOfWeek - First day of the week.
 * @property timezone - IANA timezone the athlete lives in, or `null` when unset.
 * @property accessType - Authorization tier (read-only here).
 * @property hasLocalPassword - Whether the account has a local password (false for SSO-only).
 * @property stravaLinked - Whether a Strava account is connected.
 * @property garminLinked - Whether a Garmin Connect account is connected.
 * @property photoPath - Raw backend photo path, or `null`.
 * @property avatarUrl - Servable avatar URL derived from `photoPath`, or `null`.
 * @property privacy - The user's privacy preferences.
 */
export interface ProfileDetails {
  id: number
  name: string
  username: string
  email: string
  city: string | null
  birthdate: string | null
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  height: number | null
  maxHeartRate: number | null
  preferredLanguage: Schemas['Language']
  firstDayOfWeek: Schemas['WeekDay']
  timezone: string | null
  accessType: Schemas['UserAccessType']
  hasLocalPassword: boolean
  stravaLinked: boolean
  garminLinked: boolean
  photoPath: string | null
  avatarUrl: string | null
  privacy: PrivacySettings
}

/**
 * The editable identity fields the user can change about their own profile.
 * Excludes the photo (managed by the separate upload/delete actions) and the
 * privacy settings (saved through their own endpoint).
 */
export interface ProfileEditInput {
  name: string
  username: string
  email: string
  city: string | null
  birthdate: string | null
  gender: Schemas['Gender']
  units: Schemas['Units']
  currency: Schemas['Currency']
  height: number | null
  maxHeartRate: number | null
  preferredLanguage: Schemas['Language']
  firstDayOfWeek: Schemas['WeekDay']
  /**
   * IANA timezone the athlete lives in. Used server-side as the fallback for
   * activities imported without a GPS track, which would otherwise inherit the
   * server's timezone.
   */
  timezone: string | null
}

/** Raw default-gear payload (snake_case wire shape). */
export type DefaultGearDto = Schemas['UsersDefaultGearRead']

/** Update body for the user's default gear (round-trips id + user_id). */
export type DefaultGearUpdateDto = Schemas['UsersDefaultGearUpdate']

/**
 * The user's default gear per activity type. Each field is the gear id assigned
 * as the default for that activity (or `null` for none). Mapped from
 * {@link DefaultGearDto} at the service boundary.
 *
 * @property id - Stable record identifier (round-tripped on save).
 * @property userId - Owning user id (round-tripped on save).
 */
export interface DefaultGear {
  id: number
  userId: number
  runGearId: number | null
  trailRunGearId: number | null
  virtualRunGearId: number | null
  walkGearId: number | null
  hikeGearId: number | null
  rideGearId: number | null
  mtbRideGearId: number | null
  gravelRideGearId: number | null
  virtualRideGearId: number | null
  owsGearId: number | null
  tennisGearId: number | null
  alpineSkiGearId: number | null
  nordicSkiGearId: number | null
  snowboardGearId: number | null
  windsurfGearId: number | null
}

/**
 * The editable activity→gear assignments. Excludes `id`/`userId`, which
 * round-trip from the loaded record at save time. Every value is a gear id or
 * `null`, so a single homogeneous shape backs the per-activity selectors.
 */
export type DefaultGearValues = Omit<DefaultGear, 'id' | 'userId'>
