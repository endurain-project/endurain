import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActivityType } from '@/features/activities/types'

import { useUserActivityTypesQuery } from '@/features/activities/composables/useActivities'
import { fetchUserActivityTypes } from '@/features/activities/services/activities'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchUserActivityTypes: vi.fn<() => Promise<ActivityType[]>>(() =>
    Promise.resolve(['run', 'ride', 'walk']),
  ),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

describe('activity type query', () => {
  it('shares one request between the activity and summary filters', async () => {
    let first: ReturnType<typeof useUserActivityTypesQuery> | undefined
    let second: ReturnType<typeof useUserActivityTypesQuery> | undefined
    wrapper = mount(
      defineComponent({
        setup() {
          first = useUserActivityTypesQuery()
          second = useUserActivityTypesQuery()
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
    await flushPromises()

    expect(fetchUserActivityTypes).toHaveBeenCalledTimes(1)
    expect(first?.data.value).toEqual(['run', 'ride', 'walk'])
    expect(second?.data.value).toEqual(['run', 'ride', 'walk'])
  })
})
