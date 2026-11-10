import { resolveAvatarUrl } from '@/features/auth/services/mappers'

import type { ActivityOwner } from '../types'
import type { Schemas } from '@/types'

/** Wire shape of the public user projection embedded in the activity detail and the activity feeds. */
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
