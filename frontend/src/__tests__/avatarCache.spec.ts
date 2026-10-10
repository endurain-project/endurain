import { describe, expect, it, vi } from 'vitest'

import { resolveAvatarUrl } from '@/features/auth/services/mappers'
import { bumpAvatarCacheToken, getAvatarCacheToken } from '@/lib/avatarCache'

vi.mock('@/services/runtime', () => ({
  getBackendAssetUrl: (path: string) => `https://cdn.test/${path.replace(/^\/+/, '')}`,
}))

const PHOTO_PATH = '/api/v1/users/7/photo?t=sig'

describe('avatar cache busting', () => {
  it('returns a clean, cacheable URL before any photo change', () => {
    expect(getAvatarCacheToken()).toBe(0)
    expect(resolveAvatarUrl(PHOTO_PATH)).toBe('https://cdn.test/api/v1/users/7/photo?t=sig')
  })

  it('appends a cache-busting param after a photo upload bumps the token', () => {
    bumpAvatarCacheToken()
    const token = getAvatarCacheToken()
    expect(token).toBeGreaterThan(0)
    expect(resolveAvatarUrl(PHOTO_PATH)).toBe(
      `https://cdn.test/api/v1/users/7/photo?t=sig&v=${token}`,
    )
  })

  it('still returns null when no photo is set', () => {
    expect(resolveAvatarUrl(null)).toBeNull()
  })
})
