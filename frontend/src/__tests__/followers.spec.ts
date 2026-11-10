import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  acceptFollower,
  blockUser,
  fetchBlockedUsers,
  fetchFollowers,
  fetchFollowing,
  fetchRelationship,
  followUser,
  mapFollowStatus,
  removeFollower,
  unblockUser,
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

    const { edges } = await fetchFollowers(9)

    // The endpoint is paginated, so the request asks for the largest page the
    // backend allows rather than relying on an unbounded response.
    expect(apiFetch).toHaveBeenCalledWith('/users/9/followers?num_records=200&page_number=1', {
      signal: undefined,
    })
    expect(edges).toEqual([
      { userId: 3, isAccepted: true },
      { userId: 4, isAccepted: false },
    ])
  })

  it('returns the profile of each follower from the same response', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [
        { follower_id: 3, followee_id: 9, status: 'accepted' },
        { follower_id: 4, followee_id: 9, status: 'accepted' },
      ],
      total: 2,
      page: 1,
      num_records: 200,
      next: null,
      users: { '3': { id: 3, name: 'Ada', username: 'ada', city: 'Porto', photo_path: null } },
    })

    const { profiles } = await fetchFollowers(9)

    expect(apiFetch).toHaveBeenCalledOnce()
    expect(profiles.get(3)).toMatchObject({ id: 3, name: 'Ada', username: 'ada', city: 'Porto' })
    // 4 is inactive or awaiting approval, so the server left it out: same as a 404 lookup.
    expect(profiles.get(4)).toBeNull()
  })

  it('follows every page and keeps the profiles of all of them', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        items: [{ follower_id: 3, followee_id: 9, status: 'accepted' }],
        next: 2,
        users: { '3': { id: 3, name: 'Ada', username: 'ada', city: null, photo_path: null } },
      })
      .mockResolvedValueOnce({
        items: [{ follower_id: 4, followee_id: 9, status: 'accepted' }],
        next: null,
        users: { '4': { id: 4, name: 'Bo', username: 'bo', city: null, photo_path: null } },
      })

    const { edges, profiles } = await fetchFollowers(9)

    expect(apiFetch).toHaveBeenLastCalledWith('/users/9/followers?num_records=200&page_number=2', {
      signal: undefined,
    })
    expect(edges).toEqual([
      { userId: 3, isAccepted: true },
      { userId: 4, isAccepted: true },
    ])
    expect(profiles.get(3)).toMatchObject({ username: 'ada' })
    expect(profiles.get(4)).toMatchObject({ username: 'bo' })
  })

  it('treats a null payload as an empty list', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchFollowers(9)).toEqual({ edges: [], profiles: new Map() })
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

    const { edges, profiles } = await fetchFollowing(9)

    expect(apiFetch).toHaveBeenCalledWith('/users/9/following?num_records=200&page_number=1', {
      signal: undefined,
    })
    expect(edges).toEqual([{ userId: 5, isAccepted: true }])
    expect(profiles.get(5)).toBeNull()
  })

  it('returns the profile of each followed user from the same response', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [{ follower_id: 9, followee_id: 5, status: 'accepted' }],
      total: 1,
      page: 1,
      num_records: 200,
      next: null,
      users: { '5': { id: 5, name: 'Grace', username: 'grace', city: null, photo_path: null } },
    })

    const { profiles } = await fetchFollowing(9)

    expect(profiles.get(5)).toMatchObject({ id: 5, name: 'Grace', username: 'grace' })
  })
})

describe('fetchRelationship', () => {
  it('maps the viewer’s outgoing relationship to a status and reports the block', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      outgoing: { follower_id: 1, followee_id: 2, status: 'pending' },
      incoming: null,
      is_blocked: true,
    })

    const relationship = await fetchRelationship(2)

    expect(apiFetch).toHaveBeenCalledWith('/users/2/relationship', { signal: undefined })
    expect(relationship).toEqual({ status: 'pending', isBlocked: true })
  })

  it('returns none and not blocked when there is no relationship', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchRelationship(2)).toEqual({ status: 'none', isBlocked: false })
  })
})

describe('block list', () => {
  it('lists the blocked users as public users', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      items: [{ id: 7, name: 'Bob', username: 'bob', city: null, photo_path: null }],
      total: 1,
      page: 1,
      num_records: 200,
      next: null,
    })

    const users = await fetchBlockedUsers()

    expect(apiFetch).toHaveBeenCalledWith('/profile/blocked-users?num_records=200&page_number=1', {
      signal: undefined,
    })
    expect(users.map((user) => user.username)).toEqual(['bob'])
  })

  it('blocks with PUT on the blocked-user path', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await blockUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/profile/blocked-users/7', {
      method: 'PUT',
      responseType: 'void',
    })
  })

  it('unblocks with DELETE on the blocked-user path', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await unblockUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/profile/blocked-users/7', {
      method: 'DELETE',
      responseType: 'void',
    })
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

    expect(apiFetch).toHaveBeenCalledWith('/users/2/followers', { method: 'POST' })
  })

  it('accepts a pending request by posting the accept action', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      follower_id: 3,
      followee_id: 1,
      status: 'accepted',
    })

    await acceptFollower(3)

    expect(apiFetch).toHaveBeenCalledWith('/profile/follow-requests/3/accept', {
      method: 'POST',
    })
  })

  it('unfollows with the viewer as the follower', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await unfollowUser(4, 1)

    expect(apiFetch).toHaveBeenCalledWith('/users/4/followers/1', {
      method: 'DELETE',
    })
  })

  it('removes a follower with the viewer as the followee', async () => {
    // Same route as unfollow, sides swapped -- previously two endpoints told
    // apart only by a singular/plural path segment.
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await removeFollower(5, 1)

    expect(apiFetch).toHaveBeenCalledWith('/users/1/followers/5', {
      method: 'DELETE',
    })
  })
})
