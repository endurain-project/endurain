import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  bulkImportActivities,
  importStravaActivities,
  importStravaBikes,
  importStravaShoes,
} from '@/features/import/services/import'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

describe('import service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockResolvedValue(undefined)
  })

  it('bulkImportActivities POSTs the bulk-import path (void)', async () => {
    await bulkImportActivities()
    expect(apiFetch).toHaveBeenCalledWith('/activities/bulk-import', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('importStravaActivities POSTs the Strava activities import path (void)', async () => {
    await importStravaActivities()
    expect(apiFetch).toHaveBeenCalledWith('/strava/import/activities', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('importStravaBikes POSTs the Strava bikes import path (void)', async () => {
    await importStravaBikes()
    expect(apiFetch).toHaveBeenCalledWith('/strava/import/bikes', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('importStravaShoes POSTs the Strava shoes import path (void)', async () => {
    await importStravaShoes()
    expect(apiFetch).toHaveBeenCalledWith('/strava/import/shoes', {
      method: 'POST',
      responseType: 'void',
    })
  })
})
