import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import { fetchPublicUser, mapPublicUser } from '@/features/users/services/publicUsers'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

// A `UsersRead` payload carries many fields; the public mapper only reads this
// privacy-conscious subset, so the fixture is narrowed and cast for the test.
const userDto = {
  id: 7,
  name: 'Jane Runner',
  username: 'jane',
  city: 'Lisbon',
  photo_path: '/api/v1/users/7/photo?t=sig',
} as UserDto

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
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
    const user = mapPublicUser(userDto)
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
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchPublicUser(7)).toBeNull()
  })
})
