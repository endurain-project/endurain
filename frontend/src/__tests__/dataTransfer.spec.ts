import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import { HttpError } from '@/services/http'
import {
  downloadProfileExport,
  fetchProfileExport,
  fetchProfileImport,
  importProfileData,
  requestProfileExport,
} from '@/features/profile/services/dataTransfer'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

describe('data transfer service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requestProfileExport queues the export with a POST', async () => {
    const status = { status: 'queued', failure: null, size_bytes: null } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(await requestProfileExport()).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/export', { method: 'POST' })
  })

  it('downloadProfileExport requests the archive as a blob with no timeout', async () => {
    const blob = new Blob(['archive'])
    vi.mocked(apiFetch).mockResolvedValue(blob)

    const result = await downloadProfileExport()

    expect(apiFetch).toHaveBeenCalledWith('/profile/export/download', {
      responseType: 'blob',
      timeoutMs: 0,
      signal: undefined,
    })
    expect(result).toBe(blob)
  })

  it('importProfileData posts the archive as multipart form data', async () => {
    let body: unknown
    vi.mocked(apiFetch).mockImplementation((_path, init) => {
      body = init?.body
      return Promise.resolve({ status: 'queued', failure: null, imported: null })
    })
    const file = new File(['x'], 'export.zip', { type: 'application/zip' })

    await importProfileData(file)

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/import',
      expect.objectContaining({ method: 'POST', timeoutMs: 0 }),
    )
    expect(body).toBeInstanceOf(FormData)
    const uploaded = (body as FormData).get('file')
    expect(uploaded).toBeInstanceOf(File)
    expect((uploaded as File).name).toBe('export.zip')
  })
})

describe('fetchProfileImport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads the import state', async () => {
    const status = { status: 'running', failure: null, imported: null } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(await fetchProfileImport()).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/import', { signal: undefined })
  })

  it('treats a 404 as no import recorded', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(404, 'Not Found'))

    expect(await fetchProfileImport()).toBeNull()
  })

  it('rethrows any other failure', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(500, 'Server Error'))

    await expect(fetchProfileImport()).rejects.toBeInstanceOf(HttpError)
  })
})

describe('fetchProfileExport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads the export state', async () => {
    const status = { status: 'completed', failure: null, size_bytes: 9 } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(await fetchProfileExport()).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/export', { signal: undefined })
  })

  it('treats a 404 as no export recorded', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(404, 'Not Found'))

    expect(await fetchProfileExport()).toBeNull()
  })

  it('rethrows any other failure', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(500, 'Server Error'))

    await expect(fetchProfileExport()).rejects.toBeInstanceOf(HttpError)
  })
})
