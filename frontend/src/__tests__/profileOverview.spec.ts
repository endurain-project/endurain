import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'
import { fetchUserProfileOverview } from '@/features/users/services/profileOverview'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const overview: Schemas['UserProfileOverviewRead'] = {
  user: { id: 7, name: 'Ada', username: 'ada', city: 'Lisbon', photo_path: null },
  week_stats: { run: { distance: 1000, time: 300, calories: 50 } },
  month_stats: { run: { distance: 5000, time: 1800, calories: 250 } },
  month_activity_count: 4,
  followers_count: 12,
  following_count: 8,
}

describe('fetchUserProfileOverview', () => {
  beforeEach(() => vi.mocked(apiFetch).mockReset())

  it('reads the profile summary in one request and maps the public user', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(overview)

    const result = await fetchUserProfileOverview(7, '2026-10-27')

    expect(apiFetch).toHaveBeenCalledExactlyOnceWith('/users/id/7/overview?date=2026-10-27', {
      signal: undefined,
    })
    expect(result.user).toEqual({
      id: 7,
      name: 'Ada',
      username: 'ada',
      city: 'Lisbon',
      avatarUrl: null,
    })
    expect(result.monthActivityCount).toBe(4)
    expect(result.followersCount).toBe(12)
  })
})
