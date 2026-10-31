import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, HttpError } from '@/services/http'
import { fetchActivityOwner } from '@/features/activities/services/activityOwner'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const ownerDto = {
  id: 7,
  name: 'Jane Runner',
  username: 'jane',
  photo_path: '/api/v1/users/7/photo?t=sig',
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('fetchActivityOwner', () => {
  it('uses the authenticated user endpoint when the viewer is logged in', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ownerDto)

    const owner = await fetchActivityOwner(7, true)

    expect(apiFetch).toHaveBeenCalledWith('/users/id/7', { auth: true, signal: undefined })
    expect(owner).toMatchObject({ name: 'Jane Runner', username: 'jane' })
    expect(owner?.avatarUrl).toContain('/users/7/photo?t=sig')
  })

  it('uses the public user endpoint when the viewer is anonymous', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(ownerDto)

    await fetchActivityOwner(7, false)

    expect(apiFetch).toHaveBeenCalledWith('/public/users/id/7', { auth: false, signal: undefined })
  })

  it('returns null when the public endpoint withholds the user (setting off)', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(404, 'Not Found'))
    expect(await fetchActivityOwner(7, false)).toBeNull()
  })

  it('rethrows other failures', async () => {
    vi.mocked(apiFetch).mockRejectedValueOnce(new HttpError(500, 'Server Error'))
    await expect(fetchActivityOwner(7, true)).rejects.toBeInstanceOf(HttpError)
  })
})
