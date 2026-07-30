import type { User, UserProfileDto } from '@/features/auth/types'

import { getAvatarCacheToken } from '@/lib/avatarCache'
import { getBackendAssetUrl } from '@/services/runtime'

/**
 * Coerces the backend's number/boolean-encoded flags into a real boolean.
 *
 * @param value - Raw flag from the API (`1`/`0`, `true`/`false`, or null).
 * @returns The value as a boolean.
 */
function toBoolean(value: number | boolean | null | undefined): boolean {
  return Boolean(value)
}

/**
 * Resolves the backend `photo_path` into a servable avatar URL.
 *
 * The backend returns a ready-to-use URL: a same-origin signed path
 * (`/api/v1/users/7/photo?t=…`) for local storage, or an absolute presigned URL
 * for object storage. `getBackendAssetUrl` handles both, so the client no longer
 * reverses a filesystem path.
 *
 * @param photoPath - Raw `photo_path` from the backend, or null/undefined.
 * @returns Absolute avatar URL, or `null` when no photo is set.
 */
export function resolveAvatarUrl(photoPath: string | null | undefined): string | null {
  if (!photoPath) {
    return null
  }
  const url = getBackendAssetUrl(photoPath)
  // Bust the browser cache after a photo change: the signed URL is stable, so a
  // new upload would otherwise keep showing the cached image.
  const token = getAvatarCacheToken()
  return token ? `${url}${url.includes('?') ? '&' : '?'}v=${token}` : url
}

/**
 * Maps the raw `/profile` payload to the app's clean {@link User} model.
 *
 * This is the single boundary where the backend wire format is translated, so
 * components never see snake_case or number-encoded booleans, and a schema
 * change is absorbed here instead of rippling across the UI.
 *
 * @param dto - Raw user profile payload from the backend.
 * @returns The normalized user model.
 */
export function mapUserProfile(dto: UserProfileDto): User {
  return {
    id: dto.id,
    name: dto.name,
    username: dto.username,
    email: dto.email,
    preferredLanguage: dto.preferred_language,
    accessType: dto.access_type,
    active: dto.active,
    mfaEnabled: dto.mfa_enabled,
    avatarUrl: resolveAvatarUrl(dto.photo_path),
    isStravaLinked: toBoolean(dto.is_strava_linked),
    isGarminConnectLinked: toBoolean(dto.is_garminconnect_linked),
    hasLocalPassword: dto.has_local_password ?? false,
    units: dto.units,
    currency: dto.currency,
  }
}
