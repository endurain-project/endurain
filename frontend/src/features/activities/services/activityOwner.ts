import { resolveAvatarUrl } from '@/features/auth/services/mappers'
import { apiFetch, HttpError } from '@/services/http'

import type { ActivityOwner } from '../types'
import type { Schemas } from '@/types'

/** Wire shape of the public user projection returned by the (public or authed) user endpoint. */
type ActivityOwnerDto = Schemas['UserPublicRead']

/**
 * Maps a user DTO to the minimal owner identity shown in the activity header,
 * resolving the servable avatar URL from the stored photo path.
 *
 * @param dto - The user wire payload.
 * @returns The owner identity.
 */
export function mapActivityOwner(dto: ActivityOwnerDto): ActivityOwner {
  return {
    name: dto.name,
    username: dto.username,
    avatarUrl: resolveAvatarUrl(dto.photo_path),
  }
}

/**
 * Fetches an activity owner's public-facing identity. Authenticated viewers use
 * the authenticated user endpoint; anonymous viewers use the public endpoint,
 * which the backend gates on the `public_shareable_links_user_info` server
 * setting — returning `null` (so the header falls back to a placeholder) when it
 * is disabled.
 *
 * @param userId - The owner's user id (`Activity.userId`).
 * @param authenticated - Whether the viewer is logged in.
 * @param signal - Optional abort signal (e.g. TanStack Query cancellation).
 * @returns The owner identity, or `null` when it is not available.
 */
export async function fetchActivityOwner(
  userId: number,
  authenticated: boolean,
  signal?: AbortSignal,
): Promise<ActivityOwner | null> {
  const path = authenticated ? `/users/id/${userId}` : `/public/users/id/${userId}`
  try {
    const dto = await apiFetch<ActivityOwnerDto>(path, { auth: authenticated, signal })
    return mapActivityOwner(dto)
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) {
      return null
    }
    throw error
  }
}
