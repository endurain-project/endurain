import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActivityFeedSlice, ActivityOwner } from '@/features/activities/types'

import { queryKeys } from '@/services/queryKeys'
import { fetchFollowersActivities } from '@/features/activities/services/activities'
import { fetchActivityOwner } from '@/features/activities/services/activityOwner'
import { useActivityOwnerQuery } from '@/features/activities/composables/useActivityDetail'
import { useFollowersActivitiesFeed } from '@/features/home/composables/useHome'

import { makeActivity } from './fixtures/activity'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: 1 }) }),
}))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchFollowersActivities:
    vi.fn<(cursor: string | null, numRecords: number) => Promise<ActivityFeedSlice>>(),
}))

vi.mock('@/features/activities/services/activityOwner', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activityOwner')>()),
  fetchActivityOwner: vi.fn<(userId: number) => Promise<ActivityOwner | null>>(),
}))

const jane: ActivityOwner = { name: 'Jane Runner', username: 'jane', avatarUrl: null }

const slice: ActivityFeedSlice = {
  items: [makeActivity({ id: 1, userId: 7 }), makeActivity({ id: 2, userId: 8 })],
  nextCursor: null,
  owners: new Map<number, ActivityOwner | null>([
    [7, jane],
    [8, null],
  ]),
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

describe('useFollowersActivitiesFeed', () => {
  it('seeds each owner on the slice, so the cards read them without a request', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useFollowersActivitiesFeed(1)
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.owner(7))).toEqual(jane)
    // An owner the server left out is cached as "not found" rather than looked up per card.
    expect(queryClient.getQueryData(queryKeys.activities.owner(8))).toBeNull()
    expect(queryClient.getQueryState(queryKeys.activities.owner(8))?.status).toBe('success')
  })

  it('means a card mounted afterwards makes no owner request', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useFollowersActivitiesFeed(1)
    })
    await flushPromises()
    wrapper?.unmount()

    let owner: ReturnType<typeof useActivityOwnerQuery> | undefined
    mountWith(queryClient, () => {
      owner = useActivityOwnerQuery(slice.items[0])
      useActivityOwnerQuery(slice.items[1])
    })
    await flushPromises()

    expect(owner?.data.value).toEqual(jane)
    expect(fetchActivityOwner).not.toHaveBeenCalled()
  })

  it('pages with the cursor, unaffected by the owners riding along', async () => {
    vi.mocked(fetchFollowersActivities)
      .mockResolvedValueOnce({ ...slice, nextCursor: 'next' })
      .mockResolvedValueOnce(slice)
    let feed: ReturnType<typeof useFollowersActivitiesFeed> | undefined
    mountWith(new QueryClient(), () => {
      feed = useFollowersActivitiesFeed(1)
    })
    await flushPromises()

    await feed?.fetchNextPage()
    await flushPromises()

    expect(vi.mocked(fetchFollowersActivities).mock.calls.map(([cursor]) => cursor)).toEqual([
      null,
      'next',
    ])
    expect(feed?.hasNextPage.value).toBe(false)
  })
})
