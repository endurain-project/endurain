import type { Schemas } from '@/types'
import type { UserProfileOverview } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import { mapPublicUser } from '@/features/users/services/publicUsers'

/** Fetches and maps the compact data shown at the top of a user's profile. */
export async function fetchUserProfileOverview(
  userId: number,
  anchorDate: string,
  signal?: AbortSignal,
): Promise<UserProfileOverview> {
  const params = new URLSearchParams({ date: anchorDate })
  const dto = await apiFetch<Schemas['UserProfileOverviewRead']>(
    `/users/id/${userId}/overview?${params.toString()}`,
    { signal },
  )
  return {
    user: mapPublicUser(dto.user),
    weekStats: dto.week_stats,
    monthStats: dto.month_stats,
    monthActivityCount: dto.month_activity_count,
    followersCount: dto.followers_count ?? null,
    followingCount: dto.following_count ?? null,
  }
}
