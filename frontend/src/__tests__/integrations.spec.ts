import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DateRange } from '@/features/integrations/types'

import * as realtime from '@/composables/useRealtime'
import { apiFetch } from '@/services/http'
import {
  linkGarmin,
  retrieveGarminActivities,
  retrieveGarminGear,
  retrieveGarminHealth,
  submitGarminMfa,
  unlinkGarmin,
} from '@/features/integrations/services/garmin'
import {
  buildStravaAuthUrl,
  completeStravaLink,
  retrieveStravaActivities,
  retrieveStravaGear,
  setStravaClient,
  beginStravaState,
  unlinkStrava,
} from '@/features/integrations/services/strava'
import { daysAgoRange } from '@/features/integrations/utils/dateRange'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

vi.mock('@/services/runtime', () => ({
  getRuntimeBackendHost: vi.fn<() => string | null>(() => 'https://app.example.com'),
}))

/** A Strava job as the server reports it. */
function stravaJob(kind: 'strava_link' | 'strava_unlink', status: string) {
  return { id: 'job-1', kind, status, created_at: '2026-01-01T00:00:00Z' }
}

const range: DateRange = { startDate: '2026-01-01', endDate: '2026-01-07' }

describe('daysAgoRange', () => {
  it('formats both bounds as YYYY-MM-DD spanning the requested days', () => {
    const result = daysAgoRange(7)
    expect(result.startDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(result.endDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect((Date.parse(result.endDate) - Date.parse(result.startDate)) / 86_400_000).toBe(7)
  })

  it('returns the same day for a zero-day window', () => {
    const result = daysAgoRange(0)
    expect(result.startDate).toBe(result.endDate)
  })
})

describe('strava service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockResolvedValue(undefined)
  })

  it('beginStravaState POSTs and returns the server-issued state', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({ state: 'issued-by-server' })
    await expect(beginStravaState()).resolves.toBe('issued-by-server')
    expect(apiFetch).toHaveBeenCalledWith('/strava/state', { method: 'POST' })
  })

  it('setStravaClient PUTs the client credentials with the version it read', async () => {
    await setStravaClient({ clientId: 123456, clientSecret: 'sekret' }, 4)
    expect(apiFetch).toHaveBeenCalledWith('/strava/client', {
      method: 'PUT',
      headers: { 'If-Match': '"4"' },
      body: JSON.stringify({ client_id: 123456, client_secret: 'sekret' }),
      responseType: 'void',
    })
  })

  it('buildStravaAuthUrl builds the authorize URL with an encoded redirect', () => {
    expect(buildStravaAuthUrl('mystate', 123456)).toBe(
      'https://www.strava.com/oauth/authorize?client_id=123456' +
        '&response_type=code&redirect_uri=https%3A%2F%2Fapp.example.com%2Fstrava%2Fcallback' +
        '&approval_prompt=force' +
        '&scope=read,profile:read_all,activity:read_all&state=mystate',
    )
  })

  describe('completeStravaLink', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('POSTs state, code and scope in the body, not the URL, and resolves once the queued link completes', async () => {
      vi.useFakeTimers()
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_link', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_link', 'running'))
        .mockResolvedValueOnce(stravaJob('strava_link', 'succeeded'))

      const done = completeStravaLink('st ate', 'co/de', 'read,profile:read_all,activity:read_all')
      await vi.advanceTimersByTimeAsync(2_000)
      await done

      expect(apiFetch).toHaveBeenNthCalledWith(1, '/strava/link', {
        method: 'POST',
        body: JSON.stringify({
          state: 'st ate',
          code: 'co/de',
          scope: 'read,profile:read_all,activity:read_all',
        }),
      })
      expect(apiFetch).toHaveBeenNthCalledWith(2, '/jobs/job-1', { signal: undefined })
      expect(apiFetch).toHaveBeenCalledTimes(3)
    })

    it("follows the link job's hints once the 202 gives its id", async () => {
      vi.useFakeTimers()
      const watch = vi.spyOn(realtime, 'watchJob')
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_link', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_link', 'succeeded'))

      const done = completeStravaLink('s', 'c', 'read')
      await vi.advanceTimersByTimeAsync(1_000)
      await done

      expect(watch).toHaveBeenCalledExactlyOnceWith('job-1')
      expect(watch.mock.invocationCallOrder[0]!).toBeGreaterThan(
        vi.mocked(apiFetch).mock.invocationCallOrder[0]!,
      )
      watch.mockRestore()
    })

    it('rejects when the queued link fails', async () => {
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_link', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_link', 'failed'))

      await expect(completeStravaLink('s', 'c', 'read')).rejects.toThrow('Linking Strava failed')
    })
  })

  it('retrieveStravaActivities POSTs the activities path with the window and returns the queued job', async () => {
    const job = { id: 'job-3', kind: 'activity_refresh', status: 'queued' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(retrieveStravaActivities(range)).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith(
      '/strava/activities?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST' },
    )
  })

  it('retrieveStravaGear POSTs the gear path and returns the queued job', async () => {
    const job = { id: 'job-4', kind: 'strava_gear', status: 'queued' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(retrieveStravaGear()).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith('/strava/gear', { method: 'POST' })
  })

  describe('unlinkStrava', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('DELETEs the unlink path and resolves once the queued unlink completes', async () => {
      vi.useFakeTimers()
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'running'))
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'succeeded'))

      const done = unlinkStrava()
      await vi.advanceTimersByTimeAsync(2_000)
      await done

      expect(apiFetch).toHaveBeenNthCalledWith(1, '/strava/link', { method: 'DELETE' })
      expect(apiFetch).toHaveBeenNthCalledWith(2, '/jobs/job-1', { signal: undefined })
      expect(apiFetch).toHaveBeenCalledTimes(3)
    })

    it("follows the unlink job's hints once the 202 gives its id", async () => {
      vi.useFakeTimers()
      const watch = vi.spyOn(realtime, 'watchJob')
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'succeeded'))

      const done = unlinkStrava()
      await vi.advanceTimersByTimeAsync(1_000)
      await done

      expect(watch).toHaveBeenCalledExactlyOnceWith('job-1')
      expect(watch.mock.invocationCallOrder[0]!).toBeGreaterThan(
        vi.mocked(apiFetch).mock.invocationCallOrder[0]!,
      )
      watch.mockRestore()
    })

    it('gives up when the job has not finished by the deadline', async () => {
      vi.useFakeTimers()
      vi.mocked(apiFetch).mockResolvedValue(stravaJob('strava_unlink', 'running'))

      const outcome = unlinkStrava().catch((error: unknown) => error)
      await vi.advanceTimersByTimeAsync(130_000)

      expect(((await outcome) as Error).message).toBe('Unlinking Strava did not finish in time')
    })

    it('rejects when the queued unlink fails', async () => {
      vi.mocked(apiFetch)
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'queued'))
        .mockResolvedValueOnce(stravaJob('strava_unlink', 'failed'))

      await expect(unlinkStrava()).rejects.toThrow('Unlinking Strava failed')
    })
  })
})

describe('garmin service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockResolvedValue(undefined)
  })

  it('linkGarmin POSTs the credentials and returns the queued job', async () => {
    const queued = {
      id: 'job-1',
      kind: 'garmin_link',
      status: 'queued',
      mfa_required: false,
      error_code: null,
    }
    vi.mocked(apiFetch).mockResolvedValue(queued)

    const status = await linkGarmin({ username: 'rider', password: 'pw', isCn: false })

    expect(apiFetch).toHaveBeenCalledWith('/garmin/link', {
      method: 'POST',
      body: JSON.stringify({ username: 'rider', password: 'pw', is_cn: false }),
    })
    expect(status).toEqual(queued)
  })

  it('linkGarmin forwards the China-region flag', async () => {
    await linkGarmin({ username: 'rider', password: 'pw', isCn: true })
    expect(apiFetch).toHaveBeenCalledWith('/garmin/link', {
      method: 'POST',
      body: JSON.stringify({ username: 'rider', password: 'pw', is_cn: true }),
    })
  })

  it('submitGarminMfa POSTs the code', async () => {
    await submitGarminMfa('123456')
    expect(apiFetch).toHaveBeenCalledWith('/garmin/mfa', {
      method: 'POST',
      body: JSON.stringify({ mfa_code: '123456' }),
      responseType: 'void',
    })
  })

  it('retrieveGarminActivities POSTs the activities path with the window and returns the queued job', async () => {
    const job = { id: 'job-5', kind: 'activity_refresh', status: 'queued' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(retrieveGarminActivities(range)).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith(
      '/garmin/activities?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST' },
    )
  })

  it('retrieveGarminGear POSTs the gear path and returns the queued job', async () => {
    const job = { id: 'job-6', kind: 'garmin_sync_gear', status: 'queued' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(retrieveGarminGear()).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith('/garmin/gear', { method: 'POST' })
  })

  it('retrieveGarminHealth POSTs the health path with the window and returns the queued job', async () => {
    const job = { id: 'job-7', kind: 'garmin_sync_health', status: 'queued' }
    vi.mocked(apiFetch).mockResolvedValueOnce(job)

    await expect(retrieveGarminHealth(range)).resolves.toBe(job)
    expect(apiFetch).toHaveBeenCalledWith(
      '/garmin/health?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST' },
    )
  })

  it('unlinkGarmin DELETEs the link', async () => {
    await unlinkGarmin()
    expect(apiFetch).toHaveBeenCalledWith('/garmin/link', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
