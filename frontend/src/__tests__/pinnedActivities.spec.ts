import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { type InfiniteData, QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ActivityFeedSlice, ActivitySummary } from '@/features/activities/types'
import { queryKeys } from '@/services/queryKeys'
import { fetchActivity, fetchFollowersActivities } from '@/features/activities/services/activities'
import { useUserActivitiesFeed } from '@/features/home/composables/useHome'
import {
  pinActivities,
  unpinActivity,
  updatePinnedActivities,
} from '@/features/upload/composables/usePinnedActivities'
import { replaceActivitiesInFeed } from '@/features/upload/composables/useUpload'

import { makeActivity, activityUuid } from './fixtures/activity'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))
vi.mock('@/features/activities/services/activities', () => ({
  fetchFollowersActivities: vi.fn<() => void>(),
  fetchActivity: vi.fn<() => void>(),
}))

/** A last slice of the feed holding the given activities. */
function slice(items: ActivitySummary[]): ActivityFeedSlice {
  return { items, nextCursor: null, owners: new Map() }
}

describe('useUserActivitiesFeed with pinned uploads', () => {
  beforeEach(() => {
    vi.mocked(fetchActivity).mockRejectedValue(new Error('offline'))
  })

  // The pins are module state, so each test releases the ones it made.
  afterEach(() => {
    for (const id of [2, 12, 22].map(activityUuid)) {
      unpinActivity(id)
    }
  })

  it('keeps an uploaded activity on top when a refetch returns the server ordering', async () => {
    const newest = makeActivity({ id: activityUuid(1) })
    const uploaded = makeActivity({ id: activityUuid(2), name: 'Old ride' })
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice([newest]))

    const client = new QueryClient()
    let ids: () => string[] = () => []
    let thumbnail: () => string | null = () => null
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          ids = () =>
            feed.data.value?.pages.flatMap((page) => page.items).map((activity) => activity.id) ??
            []
          thumbnail = () => feed.data.value?.pages[0]?.items[0]?.mapThumbnailUrl ?? null
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    pinActivities([uploaded])
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice([newest, uploaded]))
    await client.invalidateQueries({ queryKey: ['activities'] })
    await flushPromises()

    expect(ids()).toEqual([activityUuid(2), activityUuid(1)])

    // The thumbnail backfill updates the pin and then writes the feed cache.
    const withThumbnail = { ...uploaded, mapThumbnailUrl: 'thumb' }
    updatePinnedActivities([withThumbnail])
    client.setQueriesData<InfiniteData<ActivityFeedSlice>>(
      { queryKey: queryKeys.activities.userFeed(7, 25) },
      (data) => replaceActivitiesInFeed(data, [withThumbnail]),
    )
    await flushPromises()

    expect(ids()).toEqual([activityUuid(2), activityUuid(1)])
    expect(thumbnail()).toBe('thumb')
  })

  it('prefers a newer copy from the refetch over the stored pin', async () => {
    const uploaded = makeActivity({ id: activityUuid(12) })
    pinActivities([uploaded])
    vi.mocked(fetchFollowersActivities).mockResolvedValue(
      slice([{ ...uploaded, mapThumbnailUrl: 'late' }]),
    )

    const client = new QueryClient()
    let thumbnail: () => string | null = () => null
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          thumbnail = () => feed.data.value?.pages[0]?.items[0]?.mapThumbnailUrl ?? null
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    expect(thumbnail()).toBe('late')
  })

  it('stops showing a deleted activity once it is unpinned and the feed refetches', async () => {
    const kept = makeActivity({ id: activityUuid(21) })
    const deleted = makeActivity({ id: activityUuid(22) })
    pinActivities([deleted])
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice([kept, deleted]))

    const client = new QueryClient()
    let ids: () => string[] = () => []
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          ids = () =>
            feed.data.value?.pages.flatMap((page) => page.items).map((activity) => activity.id) ??
            []
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()
    expect(ids()).toEqual([activityUuid(22), activityUuid(21)])

    unpinActivity(activityUuid(22))
    vi.mocked(fetchFollowersActivities).mockResolvedValue(slice([kept]))
    await client.invalidateQueries({ queryKey: ['activities'] })
    await flushPromises()

    expect(ids()).toEqual([activityUuid(21)])
  })

  it('refreshes a pinned activity the feed pages do not carry when the feed refetches', async () => {
    const stale = makeActivity({ id: activityUuid(22), city: null, mapThumbnailUrl: null })
    pinActivities([stale])
    vi.mocked(fetchFollowersActivities).mockResolvedValue(
      slice([makeActivity({ id: activityUuid(21) })]),
    )

    const client = new QueryClient()
    let top: () => ActivitySummary | undefined = () => undefined
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          top = () => feed.data.value?.pages[0]?.items[0]
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()
    expect(top()?.mapThumbnailUrl).toBeNull()

    vi.mocked(fetchActivity).mockResolvedValue({ ...stale, city: 'Samora', mapThumbnailUrl: 'map' })
    await client.invalidateQueries({ queryKey: ['activities'] })
    await flushPromises()

    expect(top()).toMatchObject({ id: activityUuid(22), city: 'Samora', mapThumbnailUrl: 'map' })
  })
})
