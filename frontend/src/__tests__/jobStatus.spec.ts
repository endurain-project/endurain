import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/services/http'
import {
  fetchJob,
  followJob,
  isTerminalJobState,
  JobTimeoutError,
  listJobs,
  seedJob,
  type Job,
} from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const stop = vi.fn<() => void>()
const wait = vi.fn<(fastMs: number) => Promise<void>>()
const watchJob = vi.fn<(id: string) => { wait: typeof wait; stop: typeof stop }>()

vi.mock('@/composables/useRealtime', () => ({
  watchJob: (id: string) => watchJob(id),
}))

/** A job as `GET /jobs/{id}` answers it. */
function job(status: string, extra: Record<string, unknown> = {}): Job {
  return {
    id: '00000000-0000-4000-8000-0000000000a1',
    kind: 'user_deletion',
    status,
    created_at: '2026-01-01T00:00:00Z',
    ...extra,
  } as Job
}

beforeEach(() => {
  vi.resetAllMocks()
  watchJob.mockReturnValue({ wait, stop })
  wait.mockResolvedValue(undefined)
})

describe('isTerminalJobState', () => {
  it('treats succeeded and failed as terminal', () => {
    expect(isTerminalJobState('queued')).toBe(false)
    expect(isTerminalJobState('running')).toBe(false)
    expect(isTerminalJobState('succeeded')).toBe(true)
    expect(isTerminalJobState('failed')).toBe(true)
  })
})

describe('fetchJob', () => {
  it('encodes the id into the path, so a hostile id cannot climb out of /jobs', async () => {
    vi.mocked(apiFetch).mockResolvedValue(job('queued'))
    const controller = new AbortController()

    await fetchJob('../admin', controller.signal)

    expect(apiFetch).toHaveBeenCalledWith('/jobs/..%2Fadmin', { signal: controller.signal })
  })
})

describe('listJobs', () => {
  it('sends only the filters it is given', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], num_records: 0 })

    await listJobs()
    await listJobs({ kind: 'profile_export', status: 'running', cursor: 'c1', numRecords: 1 })

    expect(apiFetch).toHaveBeenNthCalledWith(1, '/jobs', { signal: undefined })
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/jobs?kind=profile_export&status=running&cursor=c1&num_records=1',
      { signal: undefined },
    )
  })
})

describe('seedJob', () => {
  it('puts the job in its detail entry and as the latest of its kind', () => {
    const client = new QueryClient()
    const queued = job('queued')

    seedJob(client, queued)

    expect(client.getQueryData(queryKeys.jobs.detail('00000000-0000-4000-8000-0000000000a1'))).toBe(
      queued,
    )
    expect(client.getQueryData(queryKeys.jobs.latest('user_deletion'))).toBe(queued)
  })
})

describe('followJob', () => {
  it('returns the job once it is terminal, failed included, and stops its watch', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(job('queued'))
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('failed', { error_code: 'internal' }))

    const finished = await followJob('00000000-0000-4000-8000-0000000000a1', { intervalMs: 0 })

    expect(finished.status).toBe('failed')
    expect(apiFetch).toHaveBeenCalledTimes(3)
    expect(watchJob).toHaveBeenCalledExactlyOnceWith('00000000-0000-4000-8000-0000000000a1')
    expect(wait).toHaveBeenCalledWith(0)
    expect(stop).toHaveBeenCalledOnce()
  })

  it('reads again as soon as a hint ends the wait', async () => {
    let hint!: () => void
    wait.mockReturnValueOnce(new Promise<void>((resolve) => (hint = resolve)))
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(job('running'))
      .mockResolvedValueOnce(job('succeeded'))

    const done = followJob('00000000-0000-4000-8000-0000000000a1', { intervalMs: 60_000 })
    await vi.waitFor(() => expect(wait).toHaveBeenCalledOnce())
    expect(apiFetch).toHaveBeenCalledTimes(1)

    hint()

    expect((await done).status).toBe('succeeded')
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  it('throws JobTimeoutError when the job is still running at the deadline', async () => {
    vi.mocked(apiFetch).mockResolvedValue(job('running'))

    await expect(
      followJob('00000000-0000-4000-8000-0000000000a1', { intervalMs: 0, timeoutMs: 0 }),
    ).rejects.toBeInstanceOf(JobTimeoutError)
    expect(stop).toHaveBeenCalledOnce()
  })

  it('throws when the signal is aborted, without reading again', async () => {
    const controller = new AbortController()
    vi.mocked(apiFetch).mockResolvedValue(job('running'))
    wait.mockImplementationOnce(() => {
      controller.abort(new Error('cancelled'))
      return Promise.resolve()
    })

    await expect(
      followJob('00000000-0000-4000-8000-0000000000a1', {
        intervalMs: 0,
        signal: controller.signal,
      }),
    ).rejects.toThrow('cancelled')
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(stop).toHaveBeenCalledOnce()
  })

  it('throws a failed read, a 404 included', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('404'))

    await expect(followJob('00000000-0000-4000-8000-0000000000a1')).rejects.toThrow('404')
    expect(stop).toHaveBeenCalledOnce()
  })
})
