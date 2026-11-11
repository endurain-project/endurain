import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useJobQuery, useLatestJobQuery } from '@/composables/useJobQuery'
import { HttpError } from '@/services/http'
import { fetchJob, listJobs, type Job } from '@/services/jobStatus'
import { queryKeys } from '@/services/queryKeys'

type Handler = (event: { message: string; job_id?: string }) => void

const handlers = new Set<Handler>()
const jobPollInterval = vi.fn<(fastMs: number) => number>((fastMs) => fastMs)

vi.mock('@/composables/useRealtime', () => ({
  jobPollInterval: (fastMs: number) => jobPollInterval(fastMs),
  isJobHintFor: (event: { message: string; job_id?: string }, id: string) =>
    event.message === 'JOB_STATUS_CHANGED' && event.job_id === id,
  useRealtime: () => ({
    on: (_message: string, handler: Handler) => {
      handlers.add(handler)
      return () => handlers.delete(handler)
    },
  }),
}))

vi.mock('@/services/jobStatus', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/jobStatus')>()),
  fetchJob: vi.fn<typeof fetchJob>(),
  listJobs: vi.fn<typeof listJobs>(),
}))

/** A job as `GET /jobs/{id}` answers it. */
function job(status: string, id = 'job-1'): Job {
  return {
    id,
    kind: 'garmin_link',
    status,
    mfa_required: false,
    created_at: '2026-01-01T00:00:00Z',
  } as Job
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  handlers.clear()
  vi.useRealTimers()
  vi.resetAllMocks()
  jobPollInterval.mockImplementation((fastMs) => fastMs)
})

function mountHook<T>(hook: () => T, queryClient = new QueryClient()): T {
  let result: T | undefined
  wrapper = mount(
    defineComponent({
      setup() {
        result = hook()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  return result as T
}

function announce(jobId: string): void {
  for (const handler of handlers) {
    handler({ message: 'JOB_STATUS_CHANGED', job_id: jobId })
  }
}

describe('useJobQuery', () => {
  it('reads nothing while there is no id', async () => {
    mountHook(() => useJobQuery(ref<string | null>(null), { intervalMs: 1_000 }))
    await flushPromises()

    expect(fetchJob).not.toHaveBeenCalled()
  })

  it('reads the job once an id arrives', async () => {
    vi.mocked(fetchJob).mockResolvedValue(job('queued'))
    const id = ref<string | null>(null)
    const query = mountHook(() => useJobQuery(id, { intervalMs: 1_000 }))
    await flushPromises()

    id.value = 'job-1'
    await flushPromises()

    expect(fetchJob).toHaveBeenCalledWith('job-1', expect.anything())
    expect(query.data.value?.status).toBe('queued')
  })

  it('starts from a seeded job', async () => {
    vi.mocked(fetchJob).mockReturnValue(new Promise(() => undefined))
    const client = new QueryClient()
    client.setQueryData(queryKeys.jobs.detail('job-1'), job('running'))
    const query = mountHook(() => useJobQuery('job-1', { intervalMs: 1_000 }), client)

    expect(query.data.value?.status).toBe('running')
  })

  it('polls at the interval the realtime channel gives, and stops once the job is terminal', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchJob).mockResolvedValueOnce(job('running')).mockResolvedValue(job('succeeded'))
    jobPollInterval.mockReturnValue(5_000)
    mountHook(() => useJobQuery('job-1', { intervalMs: 1_500 }))
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchJob).toHaveBeenCalledTimes(1)
    expect(jobPollInterval).toHaveBeenCalledWith(1_500)

    await vi.advanceTimersByTimeAsync(4_999)
    expect(fetchJob).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    expect(fetchJob).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchJob).toHaveBeenCalledTimes(2)
  })

  it('stops polling a job that answers 404', async () => {
    vi.useFakeTimers()
    vi.mocked(fetchJob).mockRejectedValue(new HttpError(404, 'Not Found'))
    mountHook(() => useJobQuery('job-1', { intervalMs: 1_000 }))
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchJob).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('reads again right away when a hint names the job', async () => {
    vi.mocked(fetchJob).mockResolvedValue(job('running'))
    mountHook(() => useJobQuery('job-1', { intervalMs: 60_000 }))
    await flushPromises()
    expect(fetchJob).toHaveBeenCalledTimes(1)

    announce('job-1')
    await flushPromises()

    expect(fetchJob).toHaveBeenCalledTimes(2)
  })

  it('ignores a hint for another job', async () => {
    vi.mocked(fetchJob).mockResolvedValue(job('running'))
    mountHook(() => useJobQuery('job-1', { intervalMs: 60_000 }))
    await flushPromises()

    announce('job-2')
    await flushPromises()

    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('does not read a job nobody is following when a hint arrives', async () => {
    mountHook(() => useJobQuery(null, { intervalMs: 60_000 }))
    await flushPromises()

    announce('job-1')
    await flushPromises()

    expect(fetchJob).not.toHaveBeenCalled()
  })

  it('stops listening once its scope is gone', async () => {
    vi.mocked(fetchJob).mockResolvedValue(job('running'))
    mountHook(() => useJobQuery('job-1', { intervalMs: 60_000 }))
    await flushPromises()
    wrapper?.unmount()
    wrapper = undefined

    expect(handlers.size).toBe(0)
  })
})

describe('useLatestJobQuery', () => {
  it('lists the newest job of the kind and returns the first', async () => {
    vi.mocked(listJobs).mockResolvedValue({
      items: [job('running', 'newest'), job('succeeded', 'older')],
      num_records: 1,
    })
    const query = mountHook(() => useLatestJobQuery('garmin_link'))
    await flushPromises()

    expect(listJobs).toHaveBeenCalledWith({ kind: 'garmin_link', numRecords: 1 }, expect.anything())
    expect(query.data.value?.id).toBe('newest')
  })

  it('answers null when the user has no job of the kind', async () => {
    vi.mocked(listJobs).mockResolvedValue({ items: [], num_records: 0 })
    const query = mountHook(() => useLatestJobQuery('garmin_link'))
    await flushPromises()

    expect(query.data.value).toBeNull()
  })
})
