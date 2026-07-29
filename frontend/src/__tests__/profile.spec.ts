import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ProfileDto, ProfileEditInput, PrivacySettings } from '@/features/profile/types'

import { apiFetch } from '@/services/http'
import {
  deleteProfilePhoto,
  fetchProfile,
  mapPrivacySettings,
  mapProfileDetails,
  updatePrivacySettings,
  updateProfile,
  uploadProfilePhoto,
} from '@/features/profile/services/profile'

// Deterministic avatar URL resolution (mirrors the auth mappers test).
vi.mock('@/services/runtime', () => ({
  getBackendAssetUrl: (path: string) => `https://cdn.test/${path.replace(/^\/+/, '')}`,
}))

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a full `/profile` (`UsersMe`) wire payload, overridable per case. */
function makeProfileDto(overrides: Partial<ProfileDto> = {}): ProfileDto {
  return {
    id: 5,
    name: 'Ada Lovelace',
    username: 'ada',
    email: 'ada@example.com',
    access_type: 'regular',
    active: true,
    email_verified: true,
    external_auth_count: 0,
    mfa_enabled: false,
    pending_admin_approval: false,
    preferred_language: 'en',
    gender: 'female',
    units: 'metric',
    currency: 'euro',
    first_day_of_week: 'monday',
    city: 'London',
    birthdate: '1990-01-01',
    height: 170,
    max_heart_rate: 190,
    photo_path: '/api/v1/users/5/photo?t=sig',
    default_activity_visibility: 'followers',
    hide_activity_start_time: true,
    hide_activity_location: false,
    hide_activity_map: false,
    hide_activity_hr: false,
    hide_activity_power: false,
    hide_activity_cadence: false,
    hide_activity_elevation: false,
    hide_activity_speed: false,
    hide_activity_pace: false,
    hide_activity_laps: false,
    hide_activity_workout_sets_steps: false,
    hide_activity_gear: true,
    ...overrides,
  }
}

describe('mapProfileDetails', () => {
  it('maps identity, privacy, and the derived avatar URL', () => {
    const profile = mapProfileDetails(makeProfileDto())
    expect(profile).toMatchObject({
      id: 5,
      name: 'Ada Lovelace',
      username: 'ada',
      email: 'ada@example.com',
      city: 'London',
      birthdate: '1990-01-01',
      gender: 'female',
      units: 'metric',
      currency: 'euro',
      height: 170,
      maxHeartRate: 190,
      preferredLanguage: 'en',
      firstDayOfWeek: 'monday',
      accessType: 'regular',
      avatarUrl: 'https://cdn.test/api/v1/users/5/photo?t=sig',
    })
    expect(profile.hasLocalPassword).toBe(true)
    expect(profile.privacy.defaultActivityVisibility).toBe('followers')
    expect(profile.privacy.hideStartTime).toBe(true)
    expect(profile.privacy.hideGear).toBe(true)
  })

  it('maps the athlete timezone, defaulting to null when unset', () => {
    expect(mapProfileDetails(makeProfileDto({ timezone: 'America/Los_Angeles' })).timezone).toBe(
      'America/Los_Angeles',
    )
    // Accounts that predate the setting have no value; null means "fall back to
    // the server timezone" for GPS-less activities.
    expect(mapProfileDetails(makeProfileDto({ timezone: null })).timezone).toBeNull()
    expect(mapProfileDetails(makeProfileDto()).timezone).toBeNull()
  })
})

describe('mapPrivacySettings', () => {
  it('defaults a missing visibility to public and null flags to false', () => {
    const privacy = mapPrivacySettings(
      makeProfileDto({ default_activity_visibility: null, hide_activity_start_time: null }),
    )
    expect(privacy.defaultActivityVisibility).toBe('public')
    expect(privacy.hideStartTime).toBe(false)
  })
})

describe('profile service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetchProfile reads /profile and maps the response', async () => {
    vi.mocked(apiFetch).mockResolvedValue(makeProfileDto())

    const profile = await fetchProfile()

    expect(apiFetch).toHaveBeenCalledWith('/profile', { signal: undefined })
    expect(profile.username).toBe('ada')
  })

  it('updateProfile PUTs the snake-cased editable fields', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(undefined)
    })
    const input: ProfileEditInput = {
      name: 'Ada L',
      username: 'ada',
      email: 'ada@example.com',
      city: 'Paris',
      birthdate: '1990-01-01',
      gender: 'female',
      units: 'imperial',
      currency: 'dollar',
      height: 172,
      maxHeartRate: 188,
      preferredLanguage: 'pt-PT',
      firstDayOfWeek: 'sunday',
      timezone: 'America/Los_Angeles',
    }

    await updateProfile(input)

    expect(apiFetch).toHaveBeenCalledWith('/profile', expect.objectContaining({ method: 'PUT' }))
    expect(JSON.parse(body as string)).toEqual({
      name: 'Ada L',
      username: 'ada',
      email: 'ada@example.com',
      city: 'Paris',
      birthdate: '1990-01-01',
      gender: 'female',
      units: 'imperial',
      currency: 'dollar',
      height: 172,
      max_heart_rate: 188,
      preferred_language: 'pt-PT',
      first_day_of_week: 'sunday',
      timezone: 'America/Los_Angeles',
    })
  })

  it('updatePrivacySettings PUTs the snake-cased privacy fields', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(undefined)
    })
    const privacy: PrivacySettings = {
      defaultActivityVisibility: 'private',
      hideStartTime: true,
      hideLocation: true,
      hideMap: false,
      hideHr: false,
      hidePower: false,
      hideCadence: false,
      hideElevation: false,
      hideSpeed: false,
      hidePace: false,
      hideLaps: false,
      hideWorkoutSetsSteps: false,
      hideGear: true,
    }

    await updatePrivacySettings(privacy)

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/privacy',
      expect.objectContaining({ method: 'PUT' }),
    )
    const parsed = JSON.parse(body as string) as Record<string, unknown>
    expect(parsed.default_activity_visibility).toBe('private')
    expect(parsed.hide_activity_location).toBe(true)
    expect(parsed.hide_activity_gear).toBe(true)
    expect(parsed.hide_activity_map).toBe(false)
  })

  it('uploadProfilePhoto posts the file as multipart form data', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve(undefined)
    })
    const file = new File(['x'], 'me.png', { type: 'image/png' })

    await uploadProfilePhoto(file)

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/image',
      expect.objectContaining({ method: 'POST', timeoutMs: 0 }),
    )
    expect(body).toBeInstanceOf(FormData)
    const uploaded = (body as FormData).get('file')
    expect(uploaded).toBeInstanceOf(File)
    expect((uploaded as File).name).toBe('me.png')
  })

  it('deleteProfilePhoto issues a PUT to /profile/photo', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteProfilePhoto()

    expect(apiFetch).toHaveBeenCalledWith('/profile/photo', {
      method: 'PUT',
      responseType: 'void',
    })
  })
})
