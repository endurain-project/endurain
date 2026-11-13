import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ActivityFeedSlice, ActivityMedia, ActivityOwner } from '@/features/activities/types'

import { queryKeys } from '@/services/queryKeys'
import { fetchFollowersActivities } from '@/features/activities/services/activities'
import { fetchActivityMedia } from '@/features/activities/services/activityMedia'
import {
  useActivityMediaQuery,
  useActivityOwnerQuery,
} from '@/features/activities/composables/useActivityDetail'
import {
  useFollowersActivitiesFeed,
  useUserActivitiesFeed,
} from '@/features/home/composables/useHome'

import { makeActivity, activityUuid, userUuid } from './fixtures/activity'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({ isAuthenticated: true }) }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: '00000000-0000-4000-9000-000000000001' }) }),
}))

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  fetchFollowersActivities:
    vi.fn<
      (cursor: string | null, numRecords: number, scope: string) => Promise<ActivityFeedSlice>
    >(),
}))

vi.mock('@/features/activities/services/activityMedia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activityMedia')>()),
  fetchActivityMedia: vi.fn<(activityId: string) => Promise<ActivityMedia[]>>(),
}))

vi.mock('@/features/upload/composables/usePinnedActivities', () => ({
  floatPinnedActivities: <T>(data: T) => data,
  refreshPinnedActivities: vi.fn<() => Promise<void>>(),
}))

const jane: ActivityOwner = { name: 'Jane Runner', username: 'jane', avatarUrl: null }

const slice: ActivityFeedSlice = {
  items: [
    makeActivity({ id: activityUuid(1), userId: userUuid(7) }),
    makeActivity({ id: activityUuid(2), userId: userUuid(8) }),
  ],
  nextCursor: null,
  owners: new Map<string, ActivityOwner | null>([
    [userUuid(7), jane],
    [userUuid(8), null],
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
      useFollowersActivitiesFeed(userUuid(1))
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.owner(userUuid(7)))).toEqual(jane)
    // An owner the server left out is cached as "not found" rather than looked up per card.
    expect(queryClient.getQueryData(queryKeys.activities.owner(userUuid(8)))).toBeNull()
    expect(queryClient.getQueryState(queryKeys.activities.owner(userUuid(8)))?.status).toBe(
      'success',
    )
  })

  it('means a card mounted afterwards makes no owner request', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useFollowersActivitiesFeed(userUuid(1))
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
    expect(owner?.fetchStatus.value).toBe('idle')
  })

  it('pages with the cursor, unaffected by the owners riding along', async () => {
    vi.mocked(fetchFollowersActivities)
      .mockResolvedValueOnce({ ...slice, nextCursor: 'next' })
      .mockResolvedValueOnce(slice)
    let feed: ReturnType<typeof useFollowersActivitiesFeed> | undefined
    mountWith(new QueryClient(), () => {
      feed = useFollowersActivitiesFeed(userUuid(1))
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

describe('useUserActivitiesFeed', () => {
  it('reads the own-activities cursor feed, walking next_cursor', async () => {
    vi.mocked(fetchFollowersActivities)
      .mockResolvedValueOnce({ ...slice, nextCursor: 'next' })
      .mockResolvedValueOnce(slice)
    let feed: ReturnType<typeof useUserActivitiesFeed> | undefined
    mountWith(new QueryClient(), () => {
      feed = useUserActivitiesFeed(userUuid(1))
    })
    await flushPromises()
    expect(feed?.hasNextPage.value).toBe(true)

    await feed?.fetchNextPage()
    await flushPromises()

    expect(vi.mocked(fetchFollowersActivities).mock.calls.map(([cursor]) => cursor)).toEqual([
      null,
      'next',
    ])
    expect(vi.mocked(fetchFollowersActivities).mock.calls.map(([, , scope]) => scope)).toEqual([
      'mine',
      'mine',
    ])
    expect(feed?.hasNextPage.value).toBe(false)
  })

  it('seeds the owners of the slice, the caller included', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice)
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useUserActivitiesFeed(userUuid(1))
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.owner(userUuid(7)))).toEqual(jane)
  })
})

describe('embedded activity media', () => {
  const photo: ActivityMedia = {
    id: activityUuid(5),
    activityId: activityUuid(1),
    url: `/media/${activityUuid(1)}/${activityUuid(5)}?t=abc`,
  }

  it('seeds the media of each activity on the home feed, so no card requests /media', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue({
      ...slice,
      items: [
        makeActivity({ id: activityUuid(1), media: [photo] }),
        makeActivity({ id: activityUuid(2) }),
      ],
    })
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useUserActivitiesFeed(userUuid(1))
    })
    await flushPromises()
    wrapper?.unmount()

    const galleries: ReturnType<typeof useActivityMediaQuery>[] = []
    mountWith(queryClient, () => {
      galleries.push(useActivityMediaQuery(activityUuid(1)), useActivityMediaQuery(activityUuid(2)))
    })
    await flushPromises()

    expect(galleries[0]?.data.value).toEqual([photo])
    expect(galleries[1]?.data.value).toEqual([])
    expect(fetchActivityMedia).not.toHaveBeenCalled()
  })

  it('seeds the media of the following feed too', async () => {
    vi.mocked(fetchFollowersActivities).mockResolvedValue({
      ...slice,
      items: [makeActivity({ id: activityUuid(1), userId: userUuid(7), media: [photo] })],
    })
    const queryClient = new QueryClient()
    mountWith(queryClient, () => {
      useFollowersActivitiesFeed(userUuid(1))
    })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.media(activityUuid(1)))).toEqual([photo])
  })
})
