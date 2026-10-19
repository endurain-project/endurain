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
  it('reads the accepted-followers total off the page envelope', async () => {
    // The dedicated /count endpoints are gone: `total` describes the same
    // filter, so a second round trip for a bare number is not needed.
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [], total: 12, page: 1, num_records: 1 })

    expect(await fetchFollowersCount(9)).toBe(12)
    expect(apiFetch).toHaveBeenCalledWith(
      '/followers/users/9/followers?accepted_only=true&num_records=1',
      { signal: undefined },
    )
  })

  it('reads the accepted-following total off the page envelope', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [], total: 7, page: 1, num_records: 1 })

    expect(await fetchFollowingCount(9)).toBe(7)
    expect(apiFetch).toHaveBeenCalledWith(
      '/followers/users/9/following?accepted_only=true&num_records=1',
      { signal: undefined },
    )
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

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/2/followers', { method: 'POST' })
  })

  it('accepts a pending request by patching the follow-request resource', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      follower_id: 3,
      followee_id: 1,
      status: 'accepted',
    })

    await acceptFollower(3)

    expect(apiFetch).toHaveBeenCalledWith('/followers/follow-requests/3', {
      method: 'PATCH',
      body: JSON.stringify({ status: 'accepted' }),
    })
  })

  it('unfollows with the viewer as the follower', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await unfollowUser(4, 1)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/4/followers/1', {
      method: 'DELETE',
    })
  })

  it('removes a follower with the viewer as the followee', async () => {
    // Same route as unfollow, sides swapped -- previously two endpoints told
    // apart only by a singular/plural path segment.
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await removeFollower(5, 1)

    expect(apiFetch).toHaveBeenCalledWith('/followers/users/1/followers/5', {
      method: 'DELETE',
    })
  })
})
