import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CreateUserInput, UserDto } from '@/features/users/types'

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

/** Builds a full `UserRead` wire payload, overridable per case. */
function makeUserDto(overrides: Partial<UserDto> = {}): UserDto {
  return {
    id: 7,
    version: 5,
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
    weight_units: 'imperial',
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
      weightUnits: 'imperial',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      photoPath: '/api/v1/users/7/photo?t=sig',
      avatarUrl: 'https://cdn.test/api/v1/users/7/photo?t=sig',
    })
  })

  it('normalizes a missing photo to a null avatar URL', () => {
    expect(mapManagedUser(makeUserDto({ photo_path: null })).avatarUrl).toBeNull()
  })

  it('leaves the weight units override null when the user follows units', () => {
    expect(mapManagedUser(makeUserDto({ weight_units: null })).weightUnits).toBeNull()
  })
})

describe('users service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchUsers calls the paginated endpoint and maps records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [makeUserDto()],
      total: 1,
      page: 1,
      num_records: 25,
    })

    const page = await fetchUsers({
      page: 1,
      numRecords: 25,
      showInactive: false,
      showEmailUnverified: true,
      showPendingApproval: true,
      showExternalAuth: true,
      showLocalAuth: true,
    })

    expect(apiFetch).toHaveBeenCalledWith('/users?page_number=1&num_records=25&active=true', {
      signal: undefined,
    })
    expect(page.total).toBe(1)
    expect(page.records[0]?.username).toBe('ada')
  })

  it('fetchUsers sends the username search as a server-side filter', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, page: 1, num_records: 25 })

    await fetchUsers({
      page: 1,
      numRecords: 25,
      showInactive: false,
      showEmailUnverified: true,
      showPendingApproval: true,
      showExternalAuth: true,
      showLocalAuth: true,
      username: 'a da',
    })

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toContain('&username_contains=a+da')
  })

  it('fetchUsers turns each excluded category into a state filter and omits the included ones', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, page: 1, num_records: 25 })

    await fetchUsers({
      page: 2,
      numRecords: 10,
      showInactive: false,
      showEmailUnverified: false,
      showPendingApproval: false,
      showExternalAuth: false,
      showLocalAuth: true,
    })

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe(
      '/users?page_number=2&num_records=10&active=true&email_verified=true&pending_approval=false&external_auth=false',
    )
  })

  it('fetchUsers keeps only external accounts when the local switch is off', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], total: 0, page: 1, num_records: 25 })

    await fetchUsers({
      page: 1,
      numRecords: 25,
      showInactive: true,
      showEmailUnverified: true,
      showPendingApproval: true,
      showExternalAuth: true,
      showLocalAuth: false,
    })

    expect(vi.mocked(apiFetch).mock.calls[0]?.[0]).toBe(
      '/users?page_number=1&num_records=25&external_auth=true',
    )
  })

  it('fetchUsers asks for nothing when both authentication switches are off', async () => {
    const page = await fetchUsers({
      page: 1,
      numRecords: 25,
      showInactive: true,
      showEmailUnverified: true,
      showPendingApproval: true,
      showExternalAuth: false,
      showLocalAuth: false,
    })

    expect(page).toEqual({ records: [], total: 0 })
    expect(apiFetch).not.toHaveBeenCalled()
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
      weightUnits: 'imperial',
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
        weight_units: 'imperial',
        currency: 'euro',
        preferred_language: 'en',
        gender: 'unspecified',
        first_day_of_week: 'monday',
        city: 'Lisbon',
        birthdate: '1990-01-01',
        height: 180,
        max_heart_rate: 190,
      }),
    })
  })

  it('createUser sends the administrator step-up when given one', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto())
    const input: CreateUserInput = {
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
      weightUnits: 'imperial',
      currency: 'euro',
      firstDayOfWeek: 'monday',
      city: 'Lisbon',
      birthdate: '1990-01-01',
      height: 180,
      maxHeartRate: 190,
    }

    await createUser(
      { ...input, accessType: 'admin' },
      { currentPassword: 'admin-pw', mfaCode: '123456' },
    )

    const [, init] = vi.mocked(apiFetch).mock.calls[0]!
    expect(JSON.parse(String(init?.body))).toMatchObject({
      access_type: 'admin',
      step_up: { current_password: 'admin-pw', mfa_code: '123456' },
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
      weightUnits: null,
      currency: 'euro',
      firstDayOfWeek: 'monday',
      city: 'London',
      birthdate: '1815-12-10',
      height: 170,
      maxHeartRate: 190,
    })

    expect(apiFetch).toHaveBeenCalledWith('/users/7', {
      method: 'PATCH',
      headers: { 'If-Match': '"5"' },
      body: JSON.stringify({
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
        weight_units: null,
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

    expect(apiFetch).toHaveBeenCalledWith('/users/7', { signal: undefined })
    expect(user?.username).toBe('ada')
  })

  it('fetchUserById maps a missing user to null', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchUserById(7)).toBeNull()
  })

  it('updateUser sends step_up only when the caller supplies one', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto({ email: 'new@example.com' }))
    const user = mapManagedUser(makeUserDto())
    const edits = { ...user, email: 'new@example.com', weightUnits: null }

    await updateUser(user, edits, { currentPassword: 'pw', mfaCode: '123456' })
    const [, withStepUp] = vi.mocked(apiFetch).mock.calls[0]!
    expect(JSON.parse(String(withStepUp?.body))).toMatchObject({
      email: 'new@example.com',
      step_up: { current_password: 'pw', mfa_code: '123456' },
    })

    vi.mocked(apiFetch).mockClear()
    await updateUser(user, edits)
    const [, without] = vi.mocked(apiFetch).mock.calls[0]!
    expect(JSON.parse(String(without?.body))).not.toHaveProperty('step_up')
  })

  it('updateUser sends the identity-provider proof in step_up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeUserDto())
    const user = mapManagedUser(makeUserDto())

    await updateUser(
      user,
      { ...user, weightUnits: null },
      {
        currentPassword: null,
        mfaCode: null,
        idpReauth: { ticket: 't1', codeVerifier: 'v1' },
      },
    )

    const [, init] = vi.mocked(apiFetch).mock.calls[0]!
    expect(JSON.parse(String(init?.body)).step_up).toEqual({
      current_password: null,
      mfa_code: null,
      idp_reauth: { ticket: 't1', code_verifier: 'v1' },
    })
  })

  it('changeUserPassword POSTs the new password with the admin step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await changeUserPassword(7, 'secret123', { currentPassword: 'admin-pw', mfaCode: '654321' })

    expect(apiFetch).toHaveBeenCalledWith('/users/7/password/change', {
      method: 'POST',
      body: JSON.stringify({
        password: 'secret123',
        current_password: 'admin-pw',
        mfa_code: '654321',
      }),
      responseType: 'void',
    })
  })

  it('deleteUser POSTs to the delete route with If-Match and the admin step-up', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteUser(7, 2, { currentPassword: 'admin-pw', mfaCode: null })

    expect(apiFetch).toHaveBeenCalledWith('/users/7/delete', {
      method: 'POST',
      headers: { 'If-Match': '"2"' },
      body: JSON.stringify({ current_password: 'admin-pw', mfa_code: null }),
      responseType: 'void',
    })
  })

  it('uploadUserPhoto posts a multipart body to the image endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ photo_path: 'data/user_images/7.png' })
    const file = new File(['x'], 'avatar.png', { type: 'image/png' })

    const path = await uploadUserPhoto(7, file)

    expect(path).toBe('data/user_images/7.png')
    const call = vi.mocked(apiFetch).mock.calls[0]
    expect(call?.[0]).toBe('/users/7/photo')
    expect(call?.[1]).toMatchObject({ method: 'PUT', timeoutMs: 0 })
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

  it('approveUser issues a POST to the approve endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await approveUser(7)

    expect(apiFetch).toHaveBeenCalledWith('/users/7/approve', {
      method: 'POST',
      responseType: 'void',
    })
  })
})
