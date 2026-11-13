import { describe, expect, it, vi } from 'vitest'

import type { UserProfileDto } from '@/features/auth/types'

import { mapUserProfile } from '@/features/auth/services/mappers'

vi.mock('@/services/runtime', () => ({
  getBackendAssetUrl: (path: string) => `https://cdn.test/${path.replace(/^\/+/, '')}`,
}))

const baseDto: UserProfileDto = {
  id: '00000000-0000-4000-8000-000000000007',
  name: 'Ada Lovelace',
  username: 'ada',
  email: 'ada@example.com',
  preferred_language: 'en',
  access_type: 'admin',
  active: true,
  mfa_enabled: true,
  photo_path: '/api/v1/users/7/photo?t=sig',
  is_strava_linked: true,
  is_garminconnect_linked: false,
  has_local_password: true,
  units: 'metric',
  weight_units: null,
  currency: 'euro',
  first_day_of_week: 'sunday',
}

describe('mapUserProfile', () => {
  it('maps snake_case fields to the clean camelCase model', () => {
    const user = mapUserProfile(baseDto)

    expect(user).toEqual({
      id: '00000000-0000-4000-8000-000000000007',
      name: 'Ada Lovelace',
      username: 'ada',
      email: 'ada@example.com',
      preferredLanguage: 'en',
      accessType: 'admin',
      active: true,
      mfaEnabled: true,
      avatarUrl: 'https://cdn.test/api/v1/users/7/photo?t=sig',
      isStravaLinked: true,
      isGarminConnectLinked: false,
      hasLocalPassword: true,
      units: 'metric',
      weightUnits: 'metric',
      currency: 'euro',
      firstDayOfWeek: 'sunday',
    })
  })

  it('resolves weightUnits from the explicit override, falling back to units', () => {
    expect(mapUserProfile({ ...baseDto, weight_units: 'imperial' }).weightUnits).toBe('imperial')
    expect(mapUserProfile({ ...baseDto, units: 'imperial', weight_units: null }).weightUnits).toBe(
      'imperial',
    )
  })

  it('reads the link flags', () => {
    const user = mapUserProfile({
      ...baseDto,
      is_strava_linked: false,
      is_garminconnect_linked: true,
    })

    expect(user.isStravaLinked).toBe(false)
    expect(user.isGarminConnectLinked).toBe(true)
  })

  it('treats null/undefined link flags as false', () => {
    const user = mapUserProfile({
      ...baseDto,
      is_strava_linked: null,
      is_garminconnect_linked: undefined,
    })

    expect(user.isStravaLinked).toBe(false)
    expect(user.isGarminConnectLinked).toBe(false)
  })

  it('resolves avatarUrl to null when no photo_path is set', () => {
    expect(mapUserProfile({ ...baseDto, photo_path: null }).avatarUrl).toBeNull()
    expect(mapUserProfile({ ...baseDto, photo_path: undefined }).avatarUrl).toBeNull()
  })

  it('passes the backend-issued photo URL through untouched', () => {
    // The backend signs the address; rewriting it here would break the token.
    expect(
      mapUserProfile({ ...baseDto, photo_path: '/api/v1/users/7/photo?t=a.b' }).avatarUrl,
    ).toBe('https://cdn.test/api/v1/users/7/photo?t=a.b')
  })

  it('maps hasLocalPassword straight from the payload', () => {
    expect(mapUserProfile({ ...baseDto, has_local_password: true }).hasLocalPassword).toBe(true)
    expect(mapUserProfile({ ...baseDto, has_local_password: false }).hasLocalPassword).toBe(false)
  })
})
