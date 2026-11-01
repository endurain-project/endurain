import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GarminLinkStatus } from '@/features/integrations/types'

import { useGarminLinkStatusQuery } from '@/features/integrations/composables/useIntegrations'
import { fetchGarminLinkStatus } from '@/features/integrations/services/garmin'

type Handler = (event: { message: string; job?: string }) => void

const handlers = new Set<Handler>()
const jobPollInterval = vi.fn<(fastMs: number) => number>((fastMs) => fastMs)

vi.mock('@/composables/useRealtime', () => ({
  jobPollInterval: (fastMs: number) => jobPollInterval(fastMs),
  useRealtime: () => ({
    on: (_message: string, handler: Handler) => {
      handlers.add(handler)
      return () => handlers.delete(handler)
    },
  }),
}))

vi.mock('@/features/integrations/services/garmin', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/integrations/services/garmin')>()),
  fetchGarminLinkStatus: vi.fn<() => Promise<GarminLinkStatus>>(),
}))

const pending: GarminLinkStatus = { status: 'pending', reason: null }

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  handlers.clear()
  vi.clearAllMocks()
})

function mountQuery(enabled = true) {
  let query: ReturnType<typeof useGarminLinkStatusQuery> | undefined
  wrapper = mount(
    defineComponent({
      setup() {
        query = useGarminLinkStatusQuery(ref(enabled))
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
  )
  return query as NonNullable<typeof query>
}

function announce(job: string): void {
  for (const handler of handlers) {
    handler({ message: 'JOB_STATUS_CHANGED', job })
  }
}

describe('useGarminLinkStatusQuery', () => {
  it('re-checks the link right away when a hint names it', async () => {
    vi.mocked(fetchGarminLinkStatus).mockResolvedValue(pending)
    mountQuery()
    await flushPromises()
    expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(1)

    announce('garmin-link')
    await flushPromises()

    expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(2)
  })

  it('ignores a hint for another job', async () => {
    vi.mocked(fetchGarminLinkStatus).mockResolvedValue(pending)
    mountQuery()
    await flushPromises()

    announce('strava:link')
    await flushPromises()

    expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(1)
  })

  it('does not check a link nobody is following', async () => {
    vi.mocked(fetchGarminLinkStatus).mockResolvedValue(pending)
    mountQuery(false)
    await flushPromises()

    announce('garmin-link')
    await flushPromises()

    expect(fetchGarminLinkStatus).not.toHaveBeenCalled()
  })

  it('stops listening once the dialog is gone', async () => {
    vi.mocked(fetchGarminLinkStatus).mockResolvedValue(pending)
    mountQuery()
    await flushPromises()
    wrapper?.unmount()
    wrapper = undefined

    expect(handlers.size).toBe(0)
  })

  describe('polling', () => {
    afterEach(() => {
      vi.useRealTimers()
    })

    it('polls at the interval the realtime channel gives, and stops once the attempt ends', async () => {
      vi.useFakeTimers()
      vi.mocked(fetchGarminLinkStatus)
        .mockResolvedValueOnce(pending)
        .mockResolvedValue({ status: 'completed', reason: null })
      jobPollInterval.mockReturnValue(5_000)
      mountQuery()
      await vi.advanceTimersByTimeAsync(0)
      expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(1)
      expect(jobPollInterval).toHaveBeenCalledWith(1_500)

      await vi.advanceTimersByTimeAsync(4_999)
      expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(1)
      expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(2)

      await vi.advanceTimersByTimeAsync(30_000)
      expect(fetchGarminLinkStatus).toHaveBeenCalledTimes(2)
    })
  })
})
