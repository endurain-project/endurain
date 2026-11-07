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

  it('requestProfileExport queues the export with a POST carrying the step-up credentials', async () => {
    const status = { status: 'queued', error_code: null, size_bytes: null } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(
      await requestProfileExport({ currentPassword: 'secret', mfaCode: '123456', idpReauth: null }),
    ).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/export', {
      method: 'POST',
      body: JSON.stringify({ step_up: { current_password: 'secret', mfa_code: '123456' } }),
    })
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
      return Promise.resolve({ status: 'queued', error_code: null, imported: null })
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
    const status = { status: 'running', error_code: null, imported: null } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(await fetchProfileImport()).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/import', { signal: undefined })
  })

  it('returns null when no import is recorded', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchProfileImport()).toBeNull()
  })

  it('rethrows a failure, a 404 included', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(404, 'Not Found'))

    await expect(fetchProfileImport()).rejects.toBeInstanceOf(HttpError)
  })
})

describe('fetchProfileExport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('reads the export state', async () => {
    const status = { status: 'succeeded', error_code: null, size_bytes: 9 } as const
    vi.mocked(apiFetch).mockResolvedValue(status)

    expect(await fetchProfileExport()).toEqual(status)
    expect(apiFetch).toHaveBeenCalledWith('/profile/export', { signal: undefined })
  })

  it('returns null when no export is recorded', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)

    expect(await fetchProfileExport()).toBeNull()
  })

  it('rethrows a failure, a 404 included', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(404, 'Not Found'))

    await expect(fetchProfileExport()).rejects.toBeInstanceOf(HttpError)
  })
})
