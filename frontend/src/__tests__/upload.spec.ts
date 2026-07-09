import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InfiniteData } from '@tanstack/vue-query'

import { prependActivitiesToFeed } from '@/features/upload/composables/useUpload'
import { assertValidActivityFile, uploadActivityFile } from '@/features/upload/services/upload'
import { UploadValidationError } from '@/features/upload/types'
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
  it('posts the file as multipart/form-data and returns the created activities', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: 7 }, { id: 8 }]))

    const result = await uploadActivityFile(fileOfSize('ride.gpx', 2048))

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/activities/create/upload')
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

    expect(result).toHaveLength(2)
    expect(result[0]?.id).toBe(7)
  })

  it('never interpolates a hostile filename into the request URL', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]))

    await uploadActivityFile(fileOfSize('../../../etc/passwd.gpx', 1024))

    expect(fetchMock).toHaveBeenCalledOnce()
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    // The endpoint is a fixed path; the filename only rides along as the
    // multipart part name (the server generates the stored filename).
    expect(url).toBe('/activities/create/upload')
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
