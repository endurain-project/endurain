import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DateRange } from '@/features/integrations/types'

import { apiFetch } from '@/services/http'
import {
  fetchGarminLinkStatus,
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
  clearStravaState,
  unlinkStrava,
} from '@/features/integrations/services/strava'
import { daysAgoRange } from '@/features/integrations/utils/dateRange'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

vi.mock('@/services/runtime', () => ({
  getRuntimeBackendHost: vi.fn<() => string | null>(() => 'https://app.example.com'),
}))

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

  it('clearStravaState DELETEs the state', async () => {
    await clearStravaState()
    expect(apiFetch).toHaveBeenCalledWith('/strava/state', {
      method: 'DELETE',
      responseType: 'void',
    })
  })

  it('setStravaClient PUTs the client credentials', async () => {
    await setStravaClient({ clientId: 123456, clientSecret: 'sekret' })
    expect(apiFetch).toHaveBeenCalledWith('/strava/client', {
      method: 'PUT',
      body: JSON.stringify({ client_id: 123456, client_secret: 'sekret' }),
      responseType: 'void',
    })
  })

  it('buildStravaAuthUrl builds the authorize URL with an encoded redirect', () => {
    expect(buildStravaAuthUrl('mystate', 123456)).toBe(
      'https://www.strava.com/oauth/authorize?client_id=123456' +
        '&response_type=code&redirect_uri=https%3A%2F%2Fapp.example.com%2Fstrava%2Fcallback' +
        '&approval_prompt=force' +
        '&scope=read,read_all,profile:read_all,activity:read,activity:read_all&state=mystate',
    )
  })

  describe('completeStravaLink', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('PUTs state + code in the body, not the URL, and resolves once the queued link completes', async () => {
      vi.useFakeTimers()
      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ kind: 'link', status: 'queued' })
        .mockResolvedValueOnce({ kind: 'link', status: 'running' })
        .mockResolvedValueOnce({ kind: 'link', status: 'completed' })

      const done = completeStravaLink('st ate', 'co/de')
      await vi.advanceTimersByTimeAsync(2_000)
      await done

      expect(apiFetch).toHaveBeenNthCalledWith(1, '/strava/link', {
        method: 'POST',
        body: JSON.stringify({ state: 'st ate', code: 'co/de' }),
      })
      expect(apiFetch).toHaveBeenNthCalledWith(2, '/strava/sync/link')
      expect(apiFetch).toHaveBeenCalledTimes(3)
    })

    it('rejects when the queued link fails', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce({ kind: 'link', status: 'failed' })

      await expect(completeStravaLink('s', 'c')).rejects.toThrow('Linking Strava failed')
    })
  })

  it('retrieveStravaActivities POSTs the activities path with the window', async () => {
    await retrieveStravaActivities(range)
    expect(apiFetch).toHaveBeenCalledWith(
      '/strava/activities?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST', responseType: 'void' },
    )
  })

  it('retrieveStravaGear POSTs the gear path', async () => {
    await retrieveStravaGear()
    expect(apiFetch).toHaveBeenCalledWith('/strava/gear', { method: 'POST', responseType: 'void' })
  })

  describe('unlinkStrava', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('DELETEs the unlink path and resolves once the queued unlink completes', async () => {
      vi.useFakeTimers()
      vi.mocked(apiFetch)
        .mockResolvedValueOnce({ kind: 'unlink', status: 'queued' })
        .mockResolvedValueOnce({ kind: 'unlink', status: 'running' })
        .mockResolvedValueOnce({ kind: 'unlink', status: 'completed' })

      const done = unlinkStrava()
      await vi.advanceTimersByTimeAsync(2_000)
      await done

      expect(apiFetch).toHaveBeenNthCalledWith(1, '/strava/link', { method: 'DELETE' })
      expect(apiFetch).toHaveBeenNthCalledWith(2, '/strava/sync/unlink')
      expect(apiFetch).toHaveBeenCalledTimes(3)
    })

    it('rejects when the queued unlink fails', async () => {
      vi.mocked(apiFetch).mockResolvedValueOnce({ kind: 'unlink', status: 'failed' })

      await expect(unlinkStrava()).rejects.toThrow('Unlinking Strava failed')
    })
  })
})

describe('garmin service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    vi.mocked(apiFetch).mockResolvedValue(undefined)
  })

  it('linkGarmin POSTs the credentials and returns the initial status', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ status: 'pending', reason: null })

    const status = await linkGarmin({ username: 'rider', password: 'pw', isCn: false })

    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/link', {
      method: 'POST',
      body: JSON.stringify({ username: 'rider', password: 'pw', is_cn: false }),
    })
    expect(status).toEqual({ status: 'pending', reason: null })
  })

  it('fetchGarminLinkStatus GETs the link status path', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ status: 'mfa_required', reason: null })
    const controller = new AbortController()

    const status = await fetchGarminLinkStatus(controller.signal)

    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/link/status', {
      signal: controller.signal,
    })
    expect(status.status).toBe('mfa_required')
  })

  it('linkGarmin forwards the China-region flag', async () => {
    await linkGarmin({ username: 'rider', password: 'pw', isCn: true })
    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/link', {
      method: 'POST',
      body: JSON.stringify({ username: 'rider', password: 'pw', is_cn: true }),
    })
  })

  it('submitGarminMfa POSTs the code', async () => {
    await submitGarminMfa('123456')
    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/mfa', {
      method: 'POST',
      body: JSON.stringify({ mfa_code: '123456' }),
      responseType: 'void',
    })
  })

  it('retrieveGarminActivities POSTs the activities path with the window', async () => {
    await retrieveGarminActivities(range)
    expect(apiFetch).toHaveBeenCalledWith(
      '/garminconnect/activities?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST', responseType: 'void' },
    )
  })

  it('retrieveGarminGear POSTs the gear path', async () => {
    await retrieveGarminGear()
    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/gear', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('retrieveGarminHealth POSTs the health path with the window', async () => {
    await retrieveGarminHealth(range)
    expect(apiFetch).toHaveBeenCalledWith(
      '/garminconnect/health?start_date=2026-01-01&end_date=2026-01-07',
      { method: 'POST', responseType: 'void' },
    )
  })

  it('unlinkGarmin DELETEs the link', async () => {
    await unlinkGarmin()
    expect(apiFetch).toHaveBeenCalledWith('/garminconnect/link', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
