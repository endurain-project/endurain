import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  downloadProfileExport,
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
    const status = {
      id: '00000000-0000-4000-8000-0000000000a1',
      kind: 'profile_export',
      status: 'queued',
      error_code: null,
      size_bytes: null,
    } as const
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
