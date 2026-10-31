import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  clearLogs,
  downloadLogs,
  fetchLogs,
  fetchLogsStatus,
} from '@/features/serverSettings/services/serverSettings'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const mockedApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockedApiFetch.mockReset()
})

describe('server log services', () => {
  it('reads the viewer status', async () => {
    mockedApiFetch.mockResolvedValue({ enabled: true })

    await expect(fetchLogsStatus()).resolves.toEqual({ enabled: true })
    expect(mockedApiFetch).toHaveBeenCalledWith('/server-settings/logs/status', {
      signal: undefined,
    })
  })

  it('asks for the newest records when no cursor is given', async () => {
    mockedApiFetch.mockResolvedValue({ entries: [], cursor: 0 })

    await fetchLogs({ level: null, search: '' }, null)

    expect(mockedApiFetch).toHaveBeenCalledWith('/server-settings/logs?', { signal: undefined })
  })

  it('sends the filters and the cursor', async () => {
    mockedApiFetch.mockResolvedValue({ entries: [], cursor: 9 })

    await fetchLogs({ level: 'WARNING', search: 'strava sync' }, 42)

    const [path] = mockedApiFetch.mock.calls[0]!
    const params = new URL(path, 'http://localhost').searchParams
    expect(params.get('level')).toBe('WARNING')
    expect(params.get('search')).toBe('strava sync')
    expect(params.get('after')).toBe('42')
  })

  it('downloads the log file as a blob without a timeout', async () => {
    const blob = new Blob(['log'])
    mockedApiFetch.mockResolvedValue(blob)

    await expect(downloadLogs()).resolves.toBe(blob)
    expect(mockedApiFetch).toHaveBeenCalledWith('/server-settings/logs/download', {
      responseType: 'blob',
      timeoutMs: 0,
      signal: undefined,
    })
  })

  it('clears the log with a DELETE', async () => {
    mockedApiFetch.mockResolvedValue(undefined)

    await clearLogs()

    expect(mockedApiFetch).toHaveBeenCalledWith('/server-settings/logs', {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})
