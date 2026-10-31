import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { UserDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import {
  approveUser,
  changeUserPassword,
  createUser,
  deleteUser,
  deleteUserPhoto,
  fetchUserById,
  fetchUsers,
  mapManagedUser,
  searchUsersByUsername,
  updateUser,
  uploadUserPhoto,
} from '@/features/users/services/users'

// Deterministic avatar URL resolution (mirrors the auth mappers test).
vi.mock('@/services/runtime', () => ({
  getBackendAssetUrl: (path: string) => `https://cdn.test/${path.replace(/^\/+/, '')}`,
}))

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `UsersRead` wire payload, overridable per case. */
function makeUserDto(overrides: Partial<UserDto> = {}): UserDto {
  return {
    id: 7,
    name: 'Ada Lovelace',
    username: 'ada',
    email: 'ada@example.com',
    access_type: 'admin',
    active: true,
    email_verified: true,
    pending_admin_approval: false,
    mfa_enabled: false,
    external_auth_count: 0,
    preferred_language: 'en',
    gender: 'female',
    units: 'metric',
    currency: 'euro',
    first_day_of_week: 'monday',
    city: 'London',
    birthdate: '1815-12-10',
    height: 170,
    max_heart_rate: 190,
    photo_path: '/api/v1/users/7/photo?t=sig',
    ...overrides,
  }
}

describe('mapManagedUser', () => {
  it('maps the wire shape to the clean model and derives the avatar URL', () => {
    expect(mapManagedUser(makeUserDto())).toMatchObject({
      id: 7,
      name: 'Ada Lovelace',
      username: 'ada',
      email: 'ada@example.com',
      accessType: 'admin',
      active: true,
      emailVerified: true,
      pendingAdminApproval: false,
      externalAuthCount: 0,
      preferredLanguage: 'en',
      units: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      photoPath: '/api/v1/users/7/photo?t=sig',
      avatarUrl: 'https://cdn.test/api/v1/users/7/photo?t=sig',
    })
  })

  it('normalizes a missing photo to a null avatar URL', () => {
    expect(mapManagedUser(makeUserDto({ photo_path: null })).avatarUrl).toBeNull()
  })
})

describe('users service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchUsers calls the paginated endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ records: [makeUserDto()], total: 1 })

    const page = await fetchUsers({
      page: 1,
      numRecords: 25,
      showInactive: false,
      showEmailUnverified: true,
      showPendingApproval: true,
      showExternalAuth: true,
      showLocalAuth: true,
    })

    expect(apiFetch).toHaveBeenCalledWith(
      '/users?page_number=1&num_records=25&show_inactive=false&show_email_unverified=true&show_pending_approval=true&show_external_auth=true&show_local_auth=true',
      { signal: undefined },
    )
    expect(page.total).toBe(1)
    expect(page.records[0]?.username).toBe('ada')
  })

  it('searchUsersByUsername encodes the term', async () => {
    vi.mocked(apiFetch).mockResolvedValue([makeUserDto()])

    await searchUsersByUsername('a da')

    expect(apiFetch).toHaveBeenCalledWith('/users/username/contains/a%20da', { signal: undefined })
  })

  it('createUser posts the full field payload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto())

    await createUser({
      name: 'New User',
      username: 'new',
      email: 'new@example.com',
      password: 'secret12',
      accessType: 'regular',
      active: true,
      emailVerified: true,
      pendingAdminApproval: false,
      preferredLanguage: 'en',
      gender: 'unspecified',
      units: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      city: 'Lisbon',
      birthdate: '1990-01-01',
      height: 180,
      maxHeartRate: 190,
    })

    expect(apiFetch).toHaveBeenCalledWith('/users', {
      method: 'POST',
      body: JSON.stringify({
        name: 'New User',
        username: 'new',
        email: 'new@example.com',
        password: 'secret12',
        access_type: 'regular',
        active: true,
        email_verified: true,
        pending_admin_approval: false,
        mfa_enabled: false,
        units: 'metric',
        currency: 'euro',
        preferred_language: 'en',
        gender: 'unspecified',
        first_day_of_week: 'monday',
        city: 'Lisbon',
        birthdate: '1990-01-01',
        height: 180,
        max_heart_rate: 190,
        photo_path: null,
      }),
    })
  })

  it('updateUser sends the whole record so unedited fields are preserved', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto({ name: 'Ada L.', active: false }))
    const user = mapManagedUser(makeUserDto())

    await updateUser(user, {
      name: 'Ada L.',
      username: 'ada',
      email: 'ada@example.com',
      accessType: 'regular',
      active: false,
      emailVerified: true,
      pendingAdminApproval: false,
      preferredLanguage: 'en',
      gender: 'female',
      units: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      city: 'London',
      birthdate: '1815-12-10',
      height: 170,
      maxHeartRate: 190,
    })

    expect(apiFetch).toHaveBeenCalledWith('/users/7', {
      method: 'PUT',
      body: JSON.stringify({
        id: 7,
        name: 'Ada L.',
        username: 'ada',
        email: 'ada@example.com',
        access_type: 'regular',
        active: false,
        email_verified: true,
        pending_admin_approval: false,
        preferred_language: 'en',
        gender: 'female',
        units: 'metric',
        currency: 'euro',
        first_day_of_week: 'monday',
        city: 'London',
        birthdate: '1815-12-10',
        height: 170,
        max_heart_rate: 190,
      }),
    })
  })

  it('fetchUserById fetches and maps a single user', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto())

    const user = await fetchUserById(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/id/7', { signal: undefined })
    expect(user?.username).toBe('ada')
  })

  it('fetchUserById maps a missing user to null', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchUserById(7)).toBeNull()
  })

  it('changeUserPassword PUTs the new password', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ message: 'ok' })

    await changeUserPassword(7, 'secret123')

    expect(apiFetch).toHaveBeenCalledWith('/users/7/password', {
      method: 'PUT',
      body: JSON.stringify({ password: 'secret123' }),
    })
  })

  it('deleteUser issues a DELETE for the id', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7', { method: 'DELETE', responseType: 'void' })
  })

  it('uploadUserPhoto posts a multipart body to the image endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue('data/user_images/7.png')
    const file = new File(['x'], 'avatar.png', { type: 'image/png' })

    const path = await uploadUserPhoto(7, file)

    expect(path).toBe('data/user_images/7.png')
    const call = vi.mocked(apiFetch).mock.calls[0]
    expect(call?.[0]).toBe('/users/7/image')
    expect(call?.[1]).toMatchObject({ method: 'POST', timeoutMs: 0 })
    expect(call?.[1]?.body).toBeInstanceOf(FormData)
  })

  it('deleteUserPhoto issues a DELETE for the photo', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteUserPhoto(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/photo', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('approveUser issues a PUT to the approve endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ message: 'ok' })

    await approveUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/approve', { method: 'PUT' })
  })
})
