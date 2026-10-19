import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  bulkImportFromArchive,
  bulkImportFromFolder,
  importStravaBikes,
  importStravaShoes,
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
    const job = { id: 'job-1' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(bulkImportFromFolder('strava')).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith('/activities/bulk-import/folder?source=strava', {
      method: 'POST',
    })
  })

  it('bulkImportFromArchive uploads the archive as multipart with no request timeout', async () => {
    const job = { id: 'job-2' }
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

  it('importStravaBikes uploads the CSV to the bikes import path (void)', async () => {
    await importStravaBikes(csv('bikes.csv'))

    const [path, options] = vi.mocked(apiFetch).mock.calls[0]!
    expect(path).toBe('/strava/import/bikes')
    expect(options).toMatchObject({ method: 'POST', responseType: 'void' })
    expect(((options as { body: FormData }).body.get('file') as File).name).toBe('bikes.csv')
  })

  it('importStravaShoes uploads the CSV to the shoes import path (void)', async () => {
    await importStravaShoes(csv('shoes.csv'))

    const [path, options] = vi.mocked(apiFetch).mock.calls[0]!
    expect(path).toBe('/strava/import/shoes')
    expect(options).toMatchObject({ method: 'POST', responseType: 'void' })
  })
})
