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
  id: 7,
  name: 'Jane Runner',
  username: 'jane',
  city: 'Lisbon',
  photo_path: '/api/v1/users/7/photo?t=sig',
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapEmbeddedUsers', () => {
  it('maps each referenced id from the embedded users object', () => {
    const users = mapEmbeddedUsers([7], { '7': userDto }, mapPublicUser)

    expect(users.get(7)).toMatchObject({ id: 7, name: 'Jane Runner' })
  })

  it('maps an id the server left out to null, as a lookup of that user would', () => {
    const users = mapEmbeddedUsers([7, 8], { '7': userDto }, mapPublicUser)

    expect(users.get(8)).toBeNull()
    expect(users.has(8)).toBe(true)
  })

  it('maps every id to null when the response carries no users object', () => {
    const users = mapEmbeddedUsers([7], undefined, mapPublicUser)

    expect([...users.entries()]).toEqual([[7, null]])
  })

  it('ignores embedded users nothing references, and repeated ids', () => {
    const users = mapEmbeddedUsers(
      [7, 7],
      { '7': userDto, '9': { ...userDto, id: 9 } },
      mapPublicUser,
    )

    expect([...users.keys()]).toEqual([7])
  })
})

describe('mapPublicUser', () => {
  it('keeps only public fields and resolves the avatar URL', () => {
    const user = mapPublicUser(userDto)

    expect(user).toMatchObject({ id: 7, name: 'Jane Runner', username: 'jane', city: 'Lisbon' })
    expect(user.avatarUrl).toContain('/users/7/photo?t=sig')
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

    const user = await fetchPublicUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/id/7', { signal: undefined })
    expect(user?.username).toBe('jane')
  })

  it('returns null when the user is not found', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(404, 'Not Found'))
    expect(await fetchPublicUser(7)).toBeNull()
  })
})

describe('searchPublicUsers', () => {
  it('encodes the term and maps the public projection', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([userDto])

    const users = await searchPublicUsers('a da')

    expect(apiFetch).toHaveBeenCalledWith('/users/username/contains/a%20da', { signal: undefined })
    expect(users[0]?.username).toBe('jane')
  })
})
