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
import { fetchActivityMedia } from '@/features/activities/services/activityMedia'
import {
  useActivityLapsQuery,
  useActivityMediaQuery,
  useActivityOwnerQuery,
  useActivityQuery,
  useActivitySetsQuery,
  useActivityWorkoutStepsQuery,
} from '@/features/activities/composables/useActivityDetail'

import { makeActivity, activityUuid, userUuid } from './fixtures/activity'

const ACTIVITY_ID = activityUuid(5)

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }))

vi.mock('@/features/activities/services/activityMedia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activityMedia')>()),
  fetchActivityMedia: vi.fn<(id: number) => Promise<unknown[]>>(),
}))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchActivityDetail: vi.fn<(id: number) => Promise<ActivityDetail | null>>(),
  fetchActivityLaps: vi.fn<(id: number) => Promise<unknown[]>>(),
  fetchActivitySets: vi.fn<(id: number) => Promise<unknown[]>>(),
  fetchActivityWorkoutSteps: vi.fn<(id: number) => Promise<unknown[]>>(),
}))

const lap = { id: activityUuid(1) } as ActivityDetail['laps'] extends (infer T)[] | null ? T : never

const detail: ActivityDetail = {
  activity: makeActivity({ id: ACTIVITY_ID }),
  laps: [lap],
  sets: [],
  workoutSteps: [],
  owner: null,
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
      query = useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()

    expect(query?.data.value).toEqual(detail.activity)
  })

  it('exposes null when the activity is missing or not shareable', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(null)
    let query: ReturnType<typeof useActivityQuery> | undefined
    mountWith(new QueryClient(), () => {
      query = useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()

    expect(query?.data.value).toBeNull()
  })

  it('seeds the collections it carried, so their queries make no request', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(detail)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()
    wrapper?.unmount()

    let laps: ReturnType<typeof useActivityLapsQuery> | undefined
    mountWith(queryClient, () => {
      laps = useActivityLapsQuery(ACTIVITY_ID, true)
      useActivitySetsQuery(ACTIVITY_ID, true)
      useActivityWorkoutStepsQuery(ACTIVITY_ID, true)
    })
    await flushPromises()

    expect(laps?.data.value).toEqual([lap])
    expect(queryClient.getQueryData(queryKeys.activities.sets(ACTIVITY_ID))).toEqual([])
    expect(fetchActivityLaps).not.toHaveBeenCalled()
    expect(fetchActivitySets).not.toHaveBeenCalled()
    expect(fetchActivityWorkoutSteps).not.toHaveBeenCalled()
  })

  it('seeds the media and the owner it carried, so the detail page makes no request for them', async () => {
    const photo = {
      id: activityUuid(9),
      activityId: ACTIVITY_ID,
      url: `/media/${ACTIVITY_ID}/${activityUuid(9)}?t=abc`,
    }
    const jane = { name: 'Jane Runner', username: 'jane', avatarUrl: null }
    vi.mocked(fetchActivityDetail).mockResolvedValue({
      ...detail,
      activity: makeActivity({ id: ACTIVITY_ID, userId: userUuid(7), media: [photo] }),
      owner: jane,
    })
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()
    wrapper?.unmount()

    let media: ReturnType<typeof useActivityMediaQuery> | undefined
    let owner: ReturnType<typeof useActivityOwnerQuery> | undefined
    mountWith(queryClient, () => {
      media = useActivityMediaQuery(ACTIVITY_ID)
      owner = useActivityOwnerQuery(makeActivity({ id: ACTIVITY_ID, userId: userUuid(7) }))
    })
    await flushPromises()

    expect(media?.data.value).toEqual([photo])
    expect(owner?.data.value).toEqual(jane)
    expect(media?.fetchStatus.value).toBe('idle')
    expect(owner?.fetchStatus.value).toBe('idle')
    expect(fetchActivityMedia).not.toHaveBeenCalled()
  })

  it('keeps a hidden owner as null rather than looking it up', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue({
      ...detail,
      activity: makeActivity({ id: ACTIVITY_ID, userId: userUuid(7) }),
    })
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.owner(userUuid(7)))).toBeNull()
  })

  it('leaves an incomplete collection to its own query, which reads every page', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue({ ...detail, laps: null })
    vi.mocked(fetchActivityLaps).mockResolvedValue([lap, lap])
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()
    expect(queryClient.getQueryData(queryKeys.activities.laps(ACTIVITY_ID))).toBeUndefined()
    wrapper?.unmount()

    let laps: ReturnType<typeof useActivityLapsQuery> | undefined
    mountWith(queryClient, () => {
      laps = useActivityLapsQuery(ACTIVITY_ID, true)
    })
    await flushPromises()

    expect(fetchActivityLaps).toHaveBeenCalledOnce()
    expect(laps?.data.value).toEqual([lap, lap])
  })

  it('seeds nothing when there is no activity', async () => {
    vi.mocked(fetchActivityDetail).mockResolvedValue(null)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useActivityQuery(ACTIVITY_ID)
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.laps(ACTIVITY_ID))).toBeUndefined()
  })
})
