import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { HealthChartSeries, HealthInterval } from '@/features/health/types'

import { queryKeys } from '@/services/queryKeys'
import { useHealthChartQuery } from '@/features/health/composables/useHealth'
import { fetchHealthChart } from '@/features/health/services/health'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/health/services/health', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/health/services/health')>()),
  fetchHealthChart: vi.fn<typeof fetchHealthChart>(),
}))

const weekly: HealthChartSeries = {
  bucket: 'week',
  points: [{ date: '2026-06-22', value: 27000 }],
}
const daily: HealthChartSeries = {
  bucket: 'day',
  points: [{ date: '2026-06-25', value: 8000 }],
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

describe('useHealthChartQuery', () => {
  it('loads the whole interval and refetches when the interval changes', async () => {
    vi.mocked(fetchHealthChart).mockImplementation(async (_metric, interval) =>
      interval === 'last_year' ? weekly : daily,
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const interval = ref<HealthInterval>('last_7_days')
    let data: ReturnType<typeof useHealthChartQuery>['data'] | undefined

    wrapper = mount(
      defineComponent({
        setup() {
          data = useHealthChartQuery('steps', interval).data
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    expect(fetchHealthChart).toHaveBeenCalledExactlyOnceWith(
      'steps',
      'last_7_days',
      expect.any(AbortSignal),
    )
    expect(data?.value).toEqual(daily)

    interval.value = 'last_year'
    await flushPromises()

    expect(fetchHealthChart).toHaveBeenLastCalledWith('steps', 'last_year', expect.any(AbortSignal))
    expect(data?.value).toEqual(weekly)
    expect(client.getQueryData(queryKeys.health.chart('steps', 'last_7_days'))).toEqual(daily)
    expect(client.getQueryData(queryKeys.health.chart('steps', 'last_year'))).toEqual(weekly)
  })

  it('is invalidated by the health domain prefix a write settles with', () => {
    expect(queryKeys.health.chart('sleep', 'all_time').slice(0, 1)).toEqual(queryKeys.health.all())
  })
})
