import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PublicUserDto } from '@/features/users/types'

import { apiFetch, HttpError } from '@/services/http'
import {
  fetchPublicUser,
  mapEmbeddedUsers,
  mapPublicUser,
  searchPublicUsers,
} from '@/features/users/services/publicUsers'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const userDto: PublicUserDto = {
  id: '00000000-0000-4000-8000-000000000007',
  name: 'Jane Runner',
  username: 'jane',
  city: 'Lisbon',
  photo_path: '/api/v1/users/00000000-0000-4000-8000-000000000007/photo?t=sig',
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapEmbeddedUsers', () => {
  it('maps each referenced id from the embedded users object', () => {
    const users = mapEmbeddedUsers(
      ['00000000-0000-4000-8000-000000000007'],
      { '00000000-0000-4000-8000-000000000007': userDto },
      mapPublicUser,
    )

    expect(users.get('00000000-0000-4000-8000-000000000007')).toMatchObject({
      id: '00000000-0000-4000-8000-000000000007',
      name: 'Jane Runner',
    })
  })

  it('maps an id the server left out to null, as a lookup of that user would', () => {
    const users = mapEmbeddedUsers(
      ['00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000008'],
      { '00000000-0000-4000-8000-000000000007': userDto },
      mapPublicUser,
    )

    expect(users.get('00000000-0000-4000-8000-000000000008')).toBeNull()
    expect(users.has('00000000-0000-4000-8000-000000000008')).toBe(true)
  })

  it('maps every id to null when the response carries no users object', () => {
    const users = mapEmbeddedUsers(
      ['00000000-0000-4000-8000-000000000007'],
      undefined,
      mapPublicUser,
    )

    expect([...users.entries()]).toEqual([['00000000-0000-4000-8000-000000000007', null]])
  })

  it('ignores embedded users nothing references, and repeated ids', () => {
    const users = mapEmbeddedUsers(
      ['00000000-0000-4000-8000-000000000007', '00000000-0000-4000-8000-000000000007'],
      {
        '00000000-0000-4000-8000-000000000007': userDto,
        '00000000-0000-4000-8000-000000000009': {
          ...userDto,
          id: '00000000-0000-4000-8000-000000000009',
        },
      },
      mapPublicUser,
    )

    expect([...users.keys()]).toEqual(['00000000-0000-4000-8000-000000000007'])
  })
})

describe('mapPublicUser', () => {
  it('keeps only public fields and resolves the avatar URL', () => {
    const user = mapPublicUser(userDto)

    expect(user).toMatchObject({
      id: '00000000-0000-4000-8000-000000000007',
      name: 'Jane Runner',
      username: 'jane',
      city: 'Lisbon',
    })
    expect(user.avatarUrl).toContain('/users/00000000-0000-4000-8000-000000000007/photo?t=sig')
  })

  it('keeps a null city as null', () => {
    const user = mapPublicUser({ ...userDto, city: null })
    expect(user.city).toBeNull()
  })

  it('does not expose sensitive fields', () => {
    const user = mapPublicUser({ ...userDto, email: 'jane@example.com' } as PublicUserDto)
    expect(user).not.toHaveProperty('email')
    expect(user).not.toHaveProperty('birthdate')
  })
})

describe('fetchPublicUser', () => {
  it('requests the authenticated user endpoint and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(userDto)

    const user = await fetchPublicUser('00000000-0000-4000-8000-000000000007')

    expect(apiFetch).toHaveBeenCalledWith('/users/00000000-0000-4000-8000-000000000007', {
      signal: undefined,
    })
    expect(user?.username).toBe('jane')
  })

  it('returns null when the user is not found', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(
      new HttpError(404, 'Not Found', null, 'urn:endurain:error:not-found'),
    )
    expect(await fetchPublicUser('00000000-0000-4000-8000-000000000007')).toBeNull()
  })
})

describe('searchPublicUsers', () => {
  it('encodes the term and maps the public projection', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [userDto] })

    const users = await searchPublicUsers('a da')

    expect(apiFetch).toHaveBeenCalledWith('/users?username_contains=a+da', { signal: undefined })
    expect(users[0]?.username).toBe('jane')
  })
})
