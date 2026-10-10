import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityMediaDto } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import {
  deleteActivityMedia,
  fetchActivityMedia,
  mapActivityMedia,
  uploadActivityMedia,
} from '@/features/activities/services/activityMedia'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const mediaDto: ActivityMediaDto = {
  id: 3,
  activity_id: 5,
  media_type: 1,
  url: '/api/v1/activities/5/media/3/file?t=signed-token',
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapActivityMedia', () => {
  it('uses the signed url the backend returns', () => {
    const media = mapActivityMedia(mediaDto)
    expect(media).toMatchObject({ id: 3, activityId: 5 })
    expect(media.url).toContain('/activities/5/media/3/file?t=signed-token')
  })

  it('leaves an absolute presigned url untouched', () => {
    const media = mapActivityMedia({ ...mediaDto, url: 'https://cdn.test/activity_media/5_a.jpg' })
    expect(media.url).toBe('https://cdn.test/activity_media/5_a.jpg')
  })
})

describe('fetchActivityMedia', () => {
  it('requests the activity media endpoint and maps the list', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([mediaDto])

    const media = await fetchActivityMedia(5)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5/media', { signal: undefined })
    expect(media).toHaveLength(1)
    expect(media[0]?.url).toContain('/activities/5/media/3/file?t=signed-token')
  })

  it('maps a null response to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchActivityMedia(5)).toEqual([])
  })
})

describe('uploadActivityMedia', () => {
  it('posts the file as multipart form data with no timeout', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(mediaDto)
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })

    const media = await uploadActivityMedia(5, file)

    expect(apiFetch).toHaveBeenCalledWith(
      '/activities/5/media',
      expect.objectContaining({ method: 'POST', timeoutMs: 0, body: expect.any(FormData) }),
    )
    expect(media.id).toBe(3)
  })
})

describe('deleteActivityMedia', () => {
  it('sends a DELETE to the media endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await deleteActivityMedia(5, 3)

    expect(apiFetch).toHaveBeenCalledWith('/activities/5/media/3', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
