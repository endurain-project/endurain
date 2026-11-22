import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityMediaDto } from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import {
  deleteActivityMedia,
  fetchActivityMedia,
  mapActivityMedia,
  uploadActivityMedia,
} from '@/features/activities/services/activityMedia'
import { activityUuid } from './fixtures/activity'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

const mediaDto: ActivityMediaDto = {
  id: activityUuid(3),
  activity_id: activityUuid(5),
  media_type: 'photo',
  url: `/api/v1/activities/${activityUuid(5)}/media/${activityUuid(3)}/file?t=signed-token`,
}

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

describe('mapActivityMedia', () => {
  it('uses the signed url the backend returns', () => {
    const media = mapActivityMedia(mediaDto)
    expect(media).toMatchObject({ id: activityUuid(3), activityId: activityUuid(5) })
    expect(media.url).toContain(
      `/activities/${activityUuid(5)}/media/${activityUuid(3)}/file?t=signed-token`,
    )
  })

  it('leaves an absolute presigned url untouched', () => {
    const media = mapActivityMedia({ ...mediaDto, url: 'https://cdn.test/activity_media/5_a.jpg' })
    expect(media.url).toBe('https://cdn.test/activity_media/5_a.jpg')
  })
})

describe('fetchActivityMedia', () => {
  it('requests the activity media endpoint and maps the list', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [mediaDto], next: null })

    const media = await fetchActivityMedia(activityUuid(5))

    expect(apiFetch).toHaveBeenCalledWith(
      `/activities/${activityUuid(5)}/media?num_records=200&page_number=1`,
      {
        auth: true,
        signal: undefined,
      },
    )
    expect(media).toHaveLength(1)
    expect(media[0]?.url).toContain(
      `/activities/${activityUuid(5)}/media/${activityUuid(3)}/file?t=signed-token`,
    )
  })

  it('maps an empty page to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ items: [], next: null })
    expect(await fetchActivityMedia(activityUuid(5))).toEqual([])
  })
})

describe('uploadActivityMedia', () => {
  it('posts the file as multipart form data with no timeout', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(mediaDto)
    const file = new File(['x'], 'photo.jpg', { type: 'image/jpeg' })

    const media = await uploadActivityMedia(activityUuid(5), file)

    expect(apiFetch).toHaveBeenCalledWith(
      `/activities/${activityUuid(5)}/media`,
      expect.objectContaining({ method: 'POST', timeoutMs: 0, body: expect.any(FormData) }),
    )
    expect(media.id).toBe(activityUuid(3))
  })
})

describe('deleteActivityMedia', () => {
  it('sends a DELETE to the media endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(undefined)

    await deleteActivityMedia(activityUuid(5), activityUuid(3))

    expect(apiFetch).toHaveBeenCalledWith(
      `/activities/${activityUuid(5)}/media/${activityUuid(3)}`,
      {
        method: 'DELETE',
        responseType: 'void',
      },
    )
  })
})
