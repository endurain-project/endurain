import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  bulkImportFromArchive,
  bulkImportFromFolder,
  importStravaGear,
} from '@/features/import/services/import'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

function csv(name = 'bikes.csv'): File {
  return new File(['Bike Name\n'], name, { type: 'text/csv' })
}

describe('import service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockResolvedValue(undefined)
  })

  it('bulkImportFromFolder POSTs the folder path for the chosen source and returns the one job', async () => {
    const job = { id: '00000000-0000-4000-8000-0000000000a1' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(bulkImportFromFolder('strava')).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith('/activities/bulk-import/folder?source=strava', {
      method: 'POST',
    })
  })

  it('bulkImportFromArchive uploads the archive as multipart with no request timeout', async () => {
    const job = { id: '00000000-0000-4000-8000-0000000000a2' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)
    const archive = new File(['zip'], 'export.zip', { type: 'application/zip' })

    await expect(bulkImportFromArchive(archive, 'generic')).resolves.toBe(job)

    const [path, options] = vi.mocked(apiFetch).mock.calls[0]!
    expect(path).toBe('/activities/bulk-import?source=generic')
    expect(options).toMatchObject({ method: 'POST', timeoutMs: 0 })
    const body = (options as { body: FormData }).body
    expect(body).toBeInstanceOf(FormData)
    expect((body.get('file') as File).name).toBe('export.zip')
  })

  it('bulkImportFromArchive sends the idempotency key it is given, and none otherwise', async () => {
    const archive = new File(['zip'], 'export.zip', { type: 'application/zip' })

    await bulkImportFromArchive(archive, 'generic', { idempotencyKey: 'key-1' })
    await bulkImportFromArchive(archive, 'generic')

    const [, keyed] = vi.mocked(apiFetch).mock.calls[0]!
    const [, unkeyed] = vi.mocked(apiFetch).mock.calls[1]!
    expect(keyed).toMatchObject({ headers: { 'Idempotency-Key': 'key-1' } })
    expect((unkeyed as { headers?: unknown }).headers).toBeUndefined()
  })

  it.each([
    ['bike', 'bikes.csv'],
    ['shoes', 'shoes.csv'],
  ] as const)(
    'importStravaGear uploads the %s CSV to the gear import path (void)',
    async (gearType, name) => {
      await importStravaGear(csv(name), gearType)

      const [path, options] = vi.mocked(apiFetch).mock.calls[0]!
      expect(path).toBe(`/strava/import/gear?gear_type=${gearType}`)
      expect(options).toMatchObject({ method: 'POST', responseType: 'void' })
      expect(((options as { body: FormData }).body.get('file') as File).name).toBe(name)
    },
  )
})
