import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActivityDetail } from '@/features/activities/types'

import { queryKeys } from '@/services/queryKeys'
import {
  fetchActivityDetail,
  fetchActivityLaps,
  fetchActivitySets,
  fetchActivityWorkoutSteps,
} from '@/features/activities/services/activities'
import {
  useActivityLapsQuery,
  useActivityQuery,
  useActivitySetsQuery,
  useActivityWorkoutStepsQuery,
} from '@/features/activities/composables/useActivityDetail'

import { makeActivity } from './fixtures/activity'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchActivityDetail: vi.fn<(id: number) => Promise<ActivityDetail | null>>(),
  fetchActivityLaps: vi.fn<(id: number) => Promise<unknown[]>>(),
  fetchActivitySets: vi.fn<(id: number) => Promise<unknown[]>>(),
  fetchActivityWorkoutSteps: vi.fn<(id: number) => Promise<unknown[]>>(),
}))

const lap = { id: 1 } as ActivityDetail['laps'] extends (infer T)[] | null ? T : never

const detail: ActivityDetail = {
  activity: makeActivity({ id: 5 }),
  laps: [lap],
  sets: [],
  workoutSteps: [],
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

function mountWith(queryClient: QueryClient, setup: () => void): void {
  wrapper = mount(
    defineComponent({
      setup() {
        setup()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
}

describe('useActivityQuery', () => {
  it('exposes just the activity', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(detail)
    let query: ReturnType<typeof useActivityQuery> | undefined
    mountWith(new QueryClient(), () => {
      query = useActivityQuery(5)
    })
    await flushPromises()

    expect(query?.data.value).toEqual(detail.activity)
  })

  it('exposes null when the activity is missing or not shareable', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(null)
    let query: ReturnType<typeof useActivityQuery> | undefined
    mountWith(new QueryClient(), () => {
      query = useActivityQuery(5)
    })
    await flushPromises()

    expect(query?.data.value).toBeNull()
  })

  it('seeds the collections it carried, so their queries make no request', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(detail)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(5)
    })
    await flushPromises()
    wrapper?.unmount()

    let laps: ReturnType<typeof useActivityLapsQuery> | undefined
    mountWith(queryClient, () => {
      laps = useActivityLapsQuery(5, true)
      useActivitySetsQuery(5, true)
      useActivityWorkoutStepsQuery(5, true)
    })
    await flushPromises()

    expect(laps?.data.value).toEqual([lap])
    expect(queryClient.getQueryData(queryKeys.activities.sets(5))).toEqual([])
    expect(fetchActivityLaps).not.toHaveBeenCalled()
    expect(fetchActivitySets).not.toHaveBeenCalled()
    expect(fetchActivityWorkoutSteps).not.toHaveBeenCalled()
  })

  it('leaves an incomplete collection to its own query, which reads every page', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue({ ...detail, laps: null })
    vi.mocked(fetchActivityLaps).mockResolvedValue([lap, lap])
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(5)
    })
    await flushPromises()
    expect(queryClient.getQueryData(queryKeys.activities.laps(5))).toBeUndefined()
    wrapper?.unmount()

    let laps: ReturnType<typeof useActivityLapsQuery> | undefined
    mountWith(queryClient, () => {
      laps = useActivityLapsQuery(5, true)
    })
    await flushPromises()

    expect(fetchActivityLaps).toHaveBeenCalledOnce()
    expect(laps?.data.value).toEqual([lap, lap])
  })

  it('seeds nothing when there is no activity', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(null)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(5)
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.laps(5))).toBeUndefined()
  })
})
