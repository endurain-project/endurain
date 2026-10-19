import type {
  PrivacySettings,
  PrivacyUpdateDto,
  ProfileDetails,
  ProfileDto,
  ProfileEditInput,
  ProfileUpdateDto,
} from '@/features/profile/types'

import { resolveAvatarUrl } from '@/features/auth/services/mappers'
import { apiFetch } from '@/services/http'

/**
 * Maps the privacy subset of a `/profile` payload to {@link PrivacySettings},
 * normalizing the backend's nullable columns to plain booleans and a concrete
 * default visibility.
 *
 * @param dto - Raw `/profile` payload.
 * @returns The normalized privacy settings.
 */
export function mapPrivacySettings(dto: ProfileDto): PrivacySettings {
  return {
    defaultActivityVisibility:
      (dto.default_activity_visibility as PrivacySettings['defaultActivityVisibility'] | null) ??
      'public',
    hideStartTime: dto.hide_activity_start_time ?? false,
    hideLocation: dto.hide_activity_location ?? false,
    hideMap: dto.hide_activity_map ?? false,
    hideHr: dto.hide_activity_hr ?? false,
    hidePower: dto.hide_activity_power ?? false,
    hideCadence: dto.hide_activity_cadence ?? false,
    hideElevation: dto.hide_activity_elevation ?? false,
    hideSpeed: dto.hide_activity_speed ?? false,
    hidePace: dto.hide_activity_pace ?? false,
    hideLaps: dto.hide_activity_laps ?? false,
    hideWorkoutSetsSteps: dto.hide_activity_workout_sets_steps ?? false,
    hideGear: dto.hide_activity_gear ?? false,
  }
}

/**
 * Maps a raw `/profile` (`UsersMe`) payload to the clean {@link ProfileDetails}
 * model — the single boundary where the backend wire format is normalized.
 *
 * @param dto - Raw `/profile` payload from the backend.
 * @returns The normalized self-profile model.
 */
export function mapProfileDetails(dto: ProfileDto): ProfileDetails {
  return {
    id: dto.id,
    name: dto.name,
    username: dto.username,
    email: dto.email,
    city: dto.city ?? null,
    birthdate: dto.birthdate ?? null,
    gender: dto.gender,
    units: dto.units,
    currency: dto.currency,
    height: dto.height ?? null,
    maxHeartRate: dto.max_heart_rate ?? null,
    preferredLanguage: dto.preferred_language,
    firstDayOfWeek: dto.first_day_of_week,
    timezone: dto.timezone ?? null,
    accessType: dto.access_type,
    hasLocalPassword: dto.has_local_password ?? true,
    stravaLinked: dto.is_strava_linked === 1,
    garminLinked: dto.is_garminconnect_linked === 1,
    photoPath: dto.photo_path ?? null,
    avatarUrl: resolveAvatarUrl(dto.photo_path),
    privacy: mapPrivacySettings(dto),
  }
}

/**
 * Fetches the authenticated user's full profile (identity + privacy).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The profile, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchProfile(signal?: AbortSignal): Promise<ProfileDetails> {
  const dto = await apiFetch<ProfileDto>('/profile', { signal })
  return mapProfileDetails(dto)
}

/**
 * Updates the authenticated user's editable identity fields.
 *
 * @param input - The clean profile edit input.
 * @throws {HttpError} When the request fails (e.g. duplicate username/email).
 */
export async function updateProfile(input: ProfileEditInput): Promise<void> {
  const payload: ProfileUpdateDto = {
    name: input.name,
    username: input.username,
    email: input.email,
    city: input.city,
    birthdate: input.birthdate,
    gender: input.gender,
    units: input.units,
    currency: input.currency,
    height: input.height,
    max_heart_rate: input.maxHeartRate,
    preferred_language: input.preferredLanguage,
    first_day_of_week: input.firstDayOfWeek,
    timezone: input.timezone,
  }
  await apiFetch('/profile', {
    method: 'PUT',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Updates the authenticated user's privacy settings.
 *
 * @param privacy - The clean privacy settings.
 * @throws {HttpError} When the request fails.
 */
export async function updatePrivacySettings(privacy: PrivacySettings): Promise<void> {
  const payload: PrivacyUpdateDto = {
    default_activity_visibility: privacy.defaultActivityVisibility,
    hide_activity_start_time: privacy.hideStartTime,
    hide_activity_location: privacy.hideLocation,
    hide_activity_map: privacy.hideMap,
    hide_activity_hr: privacy.hideHr,
    hide_activity_power: privacy.hidePower,
    hide_activity_cadence: privacy.hideCadence,
    hide_activity_elevation: privacy.hideElevation,
    hide_activity_speed: privacy.hideSpeed,
    hide_activity_pace: privacy.hidePace,
    hide_activity_laps: privacy.hideLaps,
    hide_activity_workout_sets_steps: privacy.hideWorkoutSetsSteps,
    hide_activity_gear: privacy.hideGear,
  }
  await apiFetch('/profile/privacy', {
    method: 'PUT',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Uploads a new profile photo. The image is sent as multipart form data under
 * the `file` field; the backend validates it and stores it under a
 * server-generated name, so the caller's filename never builds a path.
 *
 * @param file - The image to upload.
 * @throws {HttpError} When the upload fails (e.g. wrong file type).
 */
export async function uploadProfilePhoto(file: File): Promise<void> {
  const formData = new FormData()
  formData.append('file', file, file.name)
  await apiFetch('/profile/image', { method: 'POST', body: formData, timeoutMs: 0 })
}

/**
 * Removes the authenticated user's profile photo.
 *
 * @throws {HttpError} When the request fails.
 */
export async function deleteProfilePhoto(): Promise<void> {
  await apiFetch('/profile/photo', { method: 'PUT', responseType: 'void' })
}
