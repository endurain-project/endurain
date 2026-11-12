import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InfiniteData } from '@tanstack/vue-query'

import {
  prependActivitiesToFeed,
  followIngestionJob,
  replaceActivitiesInFeed,
  IngestionJobFailedError,
  IngestionJobTimeoutError,
  uploadErrorMessage,
} from '@/features/upload/composables/useUpload'
import { HttpError } from '@/services/http'
import {
  clearAwaitingThumbnail,
  isAwaitingThumbnail,
  markAwaitingThumbnail,
} from '@/features/upload/composables/usePendingThumbnails'
import { assertValidActivityFile, uploadActivityFile } from '@/features/upload/services/upload'
import {
  ACTIVITY_FILE_ACCEPT,
  type ActivityIngestionJob,
  UploadValidationError,
} from '@/features/upload/types'
import type { Activity, ActivityFeedSlice } from '@/features/activities/types'
import * as realtime from '@/composables/useRealtime'

import { makeActivity, activityUuid } from './fixtures/activity'

vi.mock('@/services/runtime', () => ({
  getApiBaseUrl: () => '',
  getRuntimeBackendHost: () => null,
  getBackendAssetUrl: (path: string) => path,
}))

vi.mock('@/services/authTokens', () => ({
  getAccessToken: vi.fn<() => string | null>(() => 'access-token'),
  getCsrfToken: vi.fn<() => string | null>(() => 'csrf-token'),
  setAuthTokens: vi.fn<() => void>(),
  clearAuthTokens: vi.fn<() => void>(),
}))

/**
 * Builds a JSON Response for a single read.
 *
 * @param body - Object to serialize.
 * @param status - HTTP status code.
 * @returns A Response instance.
 */
function jsonResponse(body: unknown, status = 201): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

/**
 * Builds an ingestion job in the shape the 202 responses return.
 *
 * @param overrides - Fields to override on the default pending upload job.
 * @returns An ingestion job.
 */
function uploadJob(overrides: Partial<ActivityIngestionJob> = {}): ActivityIngestionJob {
  return {
    id: 'job-1',
    kind: 'activity_upload',
    filename: 'ride.gpx',
    status: 'queued',
    activity_ids: [],
    created_at: '2026-07-28T10:00:00Z',
    updated_at: '2026-07-28T10:00:00Z',
    ...overrides,
  }
}

/**
 * Builds a File with a forced `size`, so size-limit branches can be exercised
 * without allocating hundreds of MiB.
 *
 * @param name - File name (drives the extension check).
 * @param size - Reported byte size.
 * @returns A File whose `size` getter returns `size`.
 */
function fileOfSize(name: string, size: number): File {
  const file = new File(['x'], name, { type: 'application/octet-stream' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

/**
 * Runs a function and returns whatever it throws, so assertions stay at the top
 * level of the test (no `expect` inside a `catch`).
 *
 * @param fn - The function expected to throw.
 * @returns The thrown value, or `undefined` when nothing was thrown.
 */
function catchError(fn: () => void): unknown {
  try {
    fn()
  } catch (error) {
    return error
  }
  return undefined
}

const fetchMock = vi.fn<(url: string, init: RequestInit) => Promise<Response>>()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ACTIVITY_FILE_ACCEPT', () => {
  it('includes extensions for desktop filtering and MIME types for iOS matching', () => {
    // Regression test: an extension-only accept filter matches nothing on
    // iOS (`.fit` has no registered UTI), greying out every file.
    for (const ext of ['.gpx', '.tcx', '.fit', '.gz']) {
      expect(ACTIVITY_FILE_ACCEPT).toContain(ext)
    }
    expect(ACTIVITY_FILE_ACCEPT).toContain('application/octet-stream')
    expect(ACTIVITY_FILE_ACCEPT).toContain('application/vnd.ant.fit')
    expect(ACTIVITY_FILE_ACCEPT).toContain('application/gzip')
  })
})

describe('assertValidActivityFile', () => {
  it('accepts each supported extension, case-insensitively', () => {
    for (const name of ['ride.gpx', 'ride.tcx', 'ride.fit', 'ride.gz', 'RIDE.GPX']) {
      expect(() => assertValidActivityFile(fileOfSize(name, 1024))).not.toThrow()
    }
  })

  it('rejects an empty file with code "empty"', () => {
    const error = catchError(() => assertValidActivityFile(fileOfSize('ride.gpx', 0)))
    expect(error).toBeInstanceOf(UploadValidationError)
    expect((error as UploadValidationError).code).toBe('empty')
  })

  it('rejects a disallowed extension with code "extension"', () => {
    const error = catchError(() => assertValidActivityFile(fileOfSize('payload.exe', 1024)))
    expect(error).toBeInstanceOf(UploadValidationError)
    expect((error as UploadValidationError).code).toBe('extension')
  })

  it('rejects an oversized file with code "size"', () => {
    const error = catchError(() =>
      assertValidActivityFile(fileOfSize('ride.gpx', 201 * 1024 * 1024)),
    )
    expect(error).toBeInstanceOf(UploadValidationError)
    expect((error as UploadValidationError).code).toBe('size')
  })
})

describe('uploadActivityFile', () => {
  it('posts the file as multipart/form-data and returns the queued job', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(uploadJob()))

    const result = await uploadActivityFile(fileOfSize('ride.gpx', 2048))

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/activities/upload')
    expect(init.method).toBe('POST')

    const body = init.body
    expect(body).toBeInstanceOf(FormData)
    const part = (body as FormData).get('file')
    expect(part).toBeInstanceOf(File)
    expect((part as File).name).toBe('ride.gpx')

    // The browser must own the multipart boundary, so the JSON content type is
    // never forced onto a FormData body.
    const headers = init.headers as Headers
    expect(headers.get('Content-Type')).toBeNull()

    // A handle to poll, not the parsed activities: parsing happens on a worker.
    expect(result.id).toBe('job-1')
    expect(result.status).toBe('queued')
  })

  it('never interpolates a hostile filename into the request URL', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(uploadJob()))

    await uploadActivityFile(fileOfSize('../../../etc/passwd.gpx', 1024))

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    // The endpoint is a fixed path; the filename only rides along as the
    // multipart part name (the server generates the stored filename).
    expect(url).toBe('/activities/upload')
    const part = (init.body as FormData).get('file')
    expect((part as File).name).toBe('../../../etc/passwd.gpx')
  })

  it('rejects invalid files before issuing any request', async () => {
    await expect(uploadActivityFile(fileOfSize('payload.exe', 1024))).rejects.toBeInstanceOf(
      UploadValidationError,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('followIngestionJob', () => {
  it('follows the hints of its own job', async () => {
    const watch = vi.spyOn(realtime, 'watchJob')
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'running' })))
      .mockResolvedValueOnce(
        jsonResponse(uploadJob({ status: 'succeeded', activity_ids: [activityUuid(7)] })),
      )

    await followIngestionJob('job-1', { intervalMs: 0 })

    expect(watch).toHaveBeenCalledExactlyOnceWith('job-1')
    watch.mockRestore()
  })

  it('stops following the hints once the import fails', async () => {
    const stop = vi.fn<() => void>()
    const watch = vi
      .spyOn(realtime, 'watchJob')
      .mockReturnValue({ wait: () => Promise.resolve(), stop })
    fetchMock.mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'failed' })))

    await expect(followIngestionJob('job-1', { intervalMs: 0 })).rejects.toThrow(
      'Activity import failed',
    )

    expect(stop).toHaveBeenCalledOnce()
    watch.mockRestore()
  })

  it('polls until the import reaches a terminal state', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'queued' })))
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'running' })))
      .mockResolvedValueOnce(
        jsonResponse(
          uploadJob({ status: 'succeeded', activity_ids: [activityUuid(7), activityUuid(8)] }),
        ),
      )

    const job = await followIngestionJob('job-1', { intervalMs: 0 })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(job.activity_ids).toEqual([activityUuid(7), activityUuid(8)])
  })

  it('keeps polling a refresh that is waiting for a provider rate limit to clear', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse(uploadJob({ status: 'queued', retry_after: '2026-01-01T12:00:00Z' })),
      )
      .mockResolvedValueOnce(
        jsonResponse(uploadJob({ status: 'succeeded', activity_ids: [activityUuid(3)] })),
      )

    const job = await followIngestionJob('job-1', { intervalMs: 0 })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(job.activity_ids).toEqual([activityUuid(3)])
  })

  it('surfaces the sanitized failure code', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(uploadJob({ status: 'failed', error_code: 'invalid_file' })),
    )

    const error = await followIngestionJob('job-1', { intervalMs: 0 }).catch((err: unknown) => err)

    expect(error).toBeInstanceOf(IngestionJobFailedError)
    expect((error as IngestionJobFailedError).code).toBe('invalid_file')
  })

  it('gives up once the deadline passes', async () => {
    fetchMock.mockResolvedValue(jsonResponse(uploadJob({ status: 'running' })))

    await expect(
      followIngestionJob('job-1', { intervalMs: 0, timeoutMs: 0 }),
    ).rejects.toBeInstanceOf(IngestionJobTimeoutError)
  })
})

/**
 * Wraps pages into an infinite-query cache value with matching page params.
 *
 * @param pages - The feed pages, newest-first.
 * @returns An {@link InfiniteData} value keyed by 1-based page number.
 */
function feed(pages: Activity[][]): InfiniteData<ActivityFeedSlice> {
  return {
    pages: pages.map((items) => ({ items, nextCursor: null, owners: new Map() })),
    pageParams: pages.map((_, index) => index + 1),
  }
}

describe('prependActivitiesToFeed', () => {
  it('pins the new activities to the top of the first page', () => {
    const result = prependActivitiesToFeed(feed([[makeActivity({ id: activityUuid(1) })]]), [
      makeActivity({ id: activityUuid(2) }),
    ])

    expect(result?.pages[0]?.items.map((activity) => activity.id)).toEqual([
      activityUuid(2),
      activityUuid(1),
    ])
  })

  it('removes an existing copy from any page before pinning it to the top', () => {
    const data = feed([
      [makeActivity({ id: activityUuid(1) })],
      [makeActivity({ id: activityUuid(2) })],
    ])

    const result = prependActivitiesToFeed(data, [makeActivity({ id: activityUuid(2) })])

    expect(result?.pages[0]?.items.map((activity) => activity.id)).toEqual([
      activityUuid(2),
      activityUuid(1),
    ])
    expect(result?.pages[1]?.items).toEqual([])
  })

  it('returns the value untouched when there is nothing cached', () => {
    expect(prependActivitiesToFeed(undefined, [makeActivity()])).toBeUndefined()
  })

  it('returns the value untouched when there are no new activities', () => {
    const data = feed([[makeActivity({ id: activityUuid(1) })]])

    expect(prependActivitiesToFeed(data, [])).toBe(data)
  })
})

describe('replaceActivitiesInFeed', () => {
  it('swaps the matching row in place, on any page', () => {
    const data = feed([
      [makeActivity({ id: activityUuid(1) })],
      [makeActivity({ id: activityUuid(2) })],
    ])

    const result = replaceActivitiesInFeed(data, [
      makeActivity({
        id: activityUuid(2),
        mapThumbnailUrl: `/api/v1/activities/${activityUuid(2)}/thumbnail?t=x`,
      }),
    ])

    expect(result?.pages[0]?.items.map((activity) => activity.id)).toEqual([activityUuid(1)])
    expect(result?.pages[1]?.items[0]?.mapThumbnailUrl).toBe(
      `/api/v1/activities/${activityUuid(2)}/thumbnail?t=x`,
    )
  })

  it('leaves rows it has no replacement for untouched', () => {
    const data = feed([
      [makeActivity({ id: activityUuid(1) }), makeActivity({ id: activityUuid(2) })],
    ])

    const result = replaceActivitiesInFeed(data, [
      makeActivity({
        id: activityUuid(2),
        mapThumbnailUrl: `/api/v1/activities/${activityUuid(2)}/thumbnail?t=x`,
      }),
    ])

    expect(result?.pages[0]?.items[0]?.mapThumbnailUrl).toBeNull()
    expect(result?.pages[0]?.items[1]?.mapThumbnailUrl).toBe(
      `/api/v1/activities/${activityUuid(2)}/thumbnail?t=x`,
    )
  })

  it('returns the value untouched when there is nothing cached', () => {
    expect(replaceActivitiesInFeed(undefined, [makeActivity()])).toBeUndefined()
  })

  it('returns the value untouched when there are no replacements', () => {
    const data = feed([[makeActivity({ id: activityUuid(1) })]])

    expect(replaceActivitiesInFeed(data, [])).toBe(data)
  })
})

describe('pending thumbnails', () => {
  afterEach(() => {
    clearAwaitingThumbnail([activityUuid(1), activityUuid(2)])
  })

  it('reports nothing as awaiting by default', () => {
    expect(isAwaitingThumbnail(activityUuid(1))).toBe(false)
  })

  it('reports marked activities as awaiting', () => {
    markAwaitingThumbnail([activityUuid(1), activityUuid(2)])

    expect(isAwaitingThumbnail(activityUuid(1))).toBe(true)
    expect(isAwaitingThumbnail(activityUuid(2))).toBe(true)
    expect(isAwaitingThumbnail(activityUuid(3))).toBe(false)
  })

  it('stops reporting an activity once it is cleared', () => {
    markAwaitingThumbnail([activityUuid(1), activityUuid(2)])

    clearAwaitingThumbnail([activityUuid(1)])

    expect(isAwaitingThumbnail(activityUuid(1))).toBe(false)
    expect(isAwaitingThumbnail(activityUuid(2))).toBe(true)
  })
})

describe('uploadErrorMessage', () => {
  const t = (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${params.seconds}` : key
  const problem = (status: number, code: string, retryAfter: number | null = null) =>
    new HttpError(status, 'x', null, `urn:endurain:error:${code}`, null, [], retryAfter)

  it.each([
    [problem(413, 'payload-too-large'), 'home.upload.tooLarge'],
    [problem(415, 'unsupported-format'), 'home.upload.failed.unsupported_format'],
    [problem(415, 'unsupported-media-type'), 'home.upload.failed.unsupported_format'],
    [problem(400, 'invalid-input'), 'home.upload.failed.invalid_file'],
    [problem(429, 'rate-limited', 12), 'app.retryAfter.tooManyAttempts:12'],
    [problem(429, 'rate-limited'), 'home.upload.error'],
    [problem(500, 'internal-error'), 'home.upload.error'],
    [problem(503, 'service-unavailable', 30), 'home.upload.error'],
    [new Error('x'), 'home.upload.error'],
    [new IngestionJobTimeoutError(), 'home.upload.timeout'],
    [new IngestionJobFailedError('no_activities_found'), 'home.upload.failed.no_activities_found'],
  ])('words %o as %s', (error, expected) => {
    expect(uploadErrorMessage(error, t)).toBe(expected)
  })
})
