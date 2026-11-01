import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useUserActivityTypeMapQuery,
  useUserActivityTypesQuery,
} from '@/features/activities/composables/useActivities'
import { fetchUserActivityTypeMap } from '@/features/activities/services/activities'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchUserActivityTypeMap: vi.fn<() => Promise<Map<number, string>>>(() =>
    Promise.resolve(
      new Map([
        [9, 'Ride'],
        [1, 'Run'],
        [11, 'Walk'],
      ]),
    ),
  ),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

describe('activity type queries', () => {
  it('share one request, so the filter codes and the summary names never fetch the types twice', async () => {
    let codes: ReturnType<typeof useUserActivityTypesQuery> | undefined
    let names: ReturnType<typeof useUserActivityTypeMapQuery> | undefined
    wrapper = mount(
      defineComponent({
        setup() {
          codes = useUserActivityTypesQuery()
          names = useUserActivityTypeMapQuery()
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
    await flushPromises()

    expect(fetchUserActivityTypeMap).toHaveBeenCalledTimes(1)
    expect(codes?.data.value).toEqual([1, 9, 11])
    expect(names?.data.value?.get(9)).toBe('Ride')
  })
})
