import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  acceptFollower,
  fetchFollowers,
  fetchFollowersCount,
  fetchFollowing,
  fetchFollowingCount,
  fetchFollowStatus,
  followUser,
  mapFollowStatus,
  removeFollower,
  unfollowUser,
} from '@/features/followers/services/followers'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapFollowStatus', () => {
  it('returns none when there is no relationship', () => {
    expect(mapFollowStatus(null)).toBe('none')
  })

  it('returns pending for an unaccepted relationship', () => {
    expect(mapFollowStatus({ follower_id: 1, followee_id: 2, status: 'pending' })).toBe('pending')
  })

  it('returns accepted for an accepted relationship', () => {
    expect(mapFollowStatus({ follower_id: 1, followee_id: 2, status: 'accepted' })).toBe('accepted')
  })
})

describe('fetchFollowers', () => {
  it('maps the *follower* (other user) from follower_id', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [
        { follower_id: 3, followee_id: 9, status: 'accepted' },
        { follower_id: 4, followee_id: 9, status: 'pending' },
      ],
      total: 2,
      page: 1,
      num_records: 200,
      next: null,
    })

    const edges = await fetchFollowers(9)

    // The endpoint is paginated, so the request asks for the largest page the
    // backend allows rather than relying on an unbounded response.
    expect(apiFetch).toHaveBeenCalledWith('/followers/users/9/followers?num_records=200', {
      signal: undefined,
    })
    expect(edges).toEqual([
      { userId: 3, isAccepted: true },
      { userId: 4, isAccepted: false },
    ])
  })

  it('treats a null payload as an empty list', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchFollowers(9)).toEqual([])
  })
})

describe('fetchFollowing', () => {
  it('maps the *followed* (other user) from followee_id', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [{ follower_id: 9, followee_id: 5, status: 'accepted' }],
      total: 1,
      page: 1,
      num_records: 200,
      next: null,
    })

    const edges = await fetchFollowing(9)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/9/following?num_records=200', {
      signal: undefined,
    })
    expect(edges).toEqual([{ userId: 5, isAccepted: true }])
  })
})

describe('follower counts', () => {
  it('requests the accepted-followers count', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(12)

    expect(await fetchFollowersCount(9)).toBe(12)
    expect(apiFetch).toHaveBeenCalledWith('/followers/users/9/followers/count?accepted_only=true', {
      signal: undefined,
    })
  })

  it('requests the accepted-following count', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(7)

    expect(await fetchFollowingCount(9)).toBe(7)
    expect(apiFetch).toHaveBeenCalledWith('/followers/users/9/following/count?accepted_only=true', {
      signal: undefined,
    })
  })
})

describe('fetchFollowStatus', () => {
  it('maps the viewer’s outgoing relationship to a status', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      outgoing: { follower_id: 1, followee_id: 2, status: 'pending' },
      incoming: null,
    })

    const status = await fetchFollowStatus(2)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/2/relationship', { signal: undefined })
    expect(status).toBe('pending')
  })

  it('returns none when there is no relationship', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchFollowStatus(2)).toBe('none')
  })
})

describe('follow-graph mutations', () => {
  it('follows via POST on the follow path', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      follower_id: 1,
      followee_id: 2,
      status: 'pending',
    })

    await followUser(2)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/2/follow', { method: 'POST' })
  })

  it('accepts a pending request via POST', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ detail: 'ok' })

    await acceptFollower(3)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/3/follow/accept', { method: 'POST' })
  })

  it('unfollows (or cancels a request) via DELETE on the follow path', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ detail: 'ok' })

    await unfollowUser(4)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/4/follow', {
      method: 'DELETE',
    })
  })

  it('removes (or declines) a follower via DELETE on the follower path', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ detail: 'ok' })

    await removeFollower(5)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/5/follower', {
      method: 'DELETE',
    })
  })
})
