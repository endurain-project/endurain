import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InfiniteData } from '@tanstack/vue-query'

import {
  prependActivitiesToFeed,
  pollUploadJob,
  UploadJobFailedError,
  UploadJobTimeoutError,
} from '@/features/upload/composables/useUpload'
import {
  assertValidActivityFile,
  fetchUploadJob,
  uploadActivityFile,
} from '@/features/upload/services/upload'
import { type ActivityUploadJob, UploadValidationError } from '@/features/upload/types'
import type { Activity } from '@/features/activities/types'

import { makeActivity } from './fixtures/activity'

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
 * Builds an upload job in the shape the 202 upload response returns.
 *
 * @param overrides - Fields to override on the default pending job.
 * @returns An upload job.
 */
function uploadJob(overrides: Partial<ActivityUploadJob> = {}): ActivityUploadJob {
  return {
    id: 'job-1',
    filename: 'ride.gpx',
    status: 'pending',
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
    expect(result.status).toBe('pending')
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

describe('fetchUploadJob', () => {
  it('encodes the job id into the path', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(uploadJob()))

    await fetchUploadJob('../admin/jobs')

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    // A hostile id must not climb out of the upload namespace.
    expect(url).toBe('/activities/upload/..%2Fadmin%2Fjobs')
  })
})

describe('pollUploadJob', () => {
  it('polls until the import reaches a terminal state', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'pending' })))
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'processing' })))
      .mockResolvedValueOnce(jsonResponse(uploadJob({ status: 'completed', activity_ids: [7, 8] })))

    const job = await pollUploadJob('job-1', { intervalMs: 0 })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(job.activity_ids).toEqual([7, 8])
  })

  it('surfaces the sanitized failure code', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(uploadJob({ status: 'failed', error_code: 'invalid_file' })),
    )

    const error = await pollUploadJob('job-1', { intervalMs: 0 }).catch((err: unknown) => err)

    expect(error).toBeInstanceOf(UploadJobFailedError)
    expect((error as UploadJobFailedError).code).toBe('invalid_file')
  })

  it('gives up once the deadline passes', async () => {
    fetchMock.mockResolvedValue(jsonResponse(uploadJob({ status: 'processing' })))

    await expect(pollUploadJob('job-1', { intervalMs: 0, timeoutMs: 0 })).rejects.toBeInstanceOf(
      UploadJobTimeoutError,
    )
  })
})

/**
 * Wraps pages into an infinite-query cache value with matching page params.
 *
 * @param pages - The feed pages, newest-first.
 * @returns An {@link InfiniteData} value keyed by 1-based page number.
 */
function feed(pages: Activity[][]): InfiniteData<Activity[]> {
  return { pages, pageParams: pages.map((_, index) => index + 1) }
}

describe('prependActivitiesToFeed', () => {
  it('pins the new activities to the top of the first page', () => {
    const result = prependActivitiesToFeed(feed([[makeActivity({ id: 1 })]]), [
      makeActivity({ id: 2 }),
    ])

    expect(result?.pages[0]?.map((activity) => activity.id)).toEqual([2, 1])
  })

  it('removes an existing copy from any page before pinning it to the top', () => {
    const data = feed([[makeActivity({ id: 1 })], [makeActivity({ id: 2 })]])

    const result = prependActivitiesToFeed(data, [makeActivity({ id: 2 })])

    expect(result?.pages[0]?.map((activity) => activity.id)).toEqual([2, 1])
    expect(result?.pages[1]).toEqual([])
  })

  it('returns the value untouched when there is nothing cached', () => {
    expect(prependActivitiesToFeed(undefined, [makeActivity()])).toBeUndefined()
  })

  it('returns the value untouched when there are no new activities', () => {
    const data = feed([[makeActivity({ id: 1 })]])

    expect(prependActivitiesToFeed(data, [])).toBe(data)
  })
})
