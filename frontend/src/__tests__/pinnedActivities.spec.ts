import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { type InfiniteData, QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Activity } from '@/features/activities/types'
import { fetchActivity, fetchUserActivities } from '@/features/activities/services/activities'
import { useUserActivitiesFeed } from '@/features/home/composables/useHome'
import {
  pinActivities,
  unpinActivity,
  updatePinnedActivities,
} from '@/features/upload/composables/usePinnedActivities'
import { replaceActivitiesInFeed } from '@/features/upload/composables/useUpload'

import { makeActivity } from './fixtures/activity'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))
vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))
vi.mock('@/features/activities/services/activities', () => ({
  fetchUserActivities: vi.fn<() => void>(),
  fetchActivity: vi.fn<() => void>(),
}))

describe('useUserActivitiesFeed with pinned uploads', () => {
  beforeEach(() => {
    vi.mocked(fetchActivity).mockRejectedValue(new Error('offline'))
  })

  // The pins are module state, so each test releases the ones it made.
  afterEach(() => {
    for (const id of [2, 12, 22]) {
      unpinActivity(id)
    }
  })

  it('keeps an uploaded activity on top when a refetch returns the server ordering', async () => {
    const newest = makeActivity({ id: 1 })
    const uploaded = makeActivity({ id: 2, name: 'Old ride' })
    vi.mocked(fetchUserActivities).mockResolvedValue([newest])

    const client = new QueryClient()
    let ids: () => number[] = () => []
    let thumbnail: () => string | null = () => null
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          ids = () => feed.data.value?.pages.flat().map((activity) => activity.id) ?? []
          thumbnail = () => feed.data.value?.pages[0]?.[0]?.mapThumbnailUrl ?? null
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    pinActivities([uploaded])
    vi.mocked(fetchUserActivities).mockResolvedValue([newest, uploaded])
    await client.invalidateQueries({ queryKey: ['activities'] })
    await flushPromises()

    expect(ids()).toEqual([2, 1])

    // The thumbnail backfill updates the pin and then writes the feed cache.
    const withThumbnail = { ...uploaded, mapThumbnailUrl: 'thumb' }
    updatePinnedActivities([withThumbnail])
    client.setQueriesData<InfiniteData<Activity[]>>({ queryKey: ['activities'] }, (data) =>
      replaceActivitiesInFeed(data, [withThumbnail]),
    )
    await flushPromises()

    expect(ids()).toEqual([2, 1])
    expect(thumbnail()).toBe('thumb')
  })

  it('prefers a newer copy from the refetch over the stored pin', async () => {
    const uploaded = makeActivity({ id: 12 })
    pinActivities([uploaded])
    vi.mocked(fetchUserActivities).mockResolvedValue([{ ...uploaded, mapThumbnailUrl: 'late' }])

    const client = new QueryClient()
    let thumbnail: () => string | null = () => null
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          thumbnail = () => feed.data.value?.pages[0]?.[0]?.mapThumbnailUrl ?? null
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()

    expect(thumbnail()).toBe('late')
  })

  it('stops showing a deleted activity once it is unpinned and the feed refetches', async () => {
    const kept = makeActivity({ id: 21 })
    const deleted = makeActivity({ id: 22 })
    pinActivities([deleted])
    vi.mocked(fetchUserActivities).mockResolvedValue([kept, deleted])

    const client = new QueryClient()
    let ids: () => number[] = () => []
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          ids = () => feed.data.value?.pages.flat().map((activity) => activity.id) ?? []
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    await flushPromises()
    expect(ids()).toEqual([22, 21])

    unpinActivity(22)
    vi.mocked(fetchUserActivities).mockResolvedValue([kept])
    await client.invalidateQueries({ queryKey: ['activities'] })
    await flushPromises()

    expect(ids()).toEqual([21])
  })

  it('refreshes a pinned activity the feed pages do not carry when the feed refetches', async () => {
    const stale = makeActivity({ id: 22, city: null, mapThumbnailUrl: null })
    pinActivities([stale])
    vi.mocked(fetchUserActivities).mockResolvedValue([makeActivity({ id: 21 })])

    const client = new QueryClient()
    let top: () => Activity | undefined = () => undefined
    mount(
      defineComponent({
        setup() {
          const feed = useUserActivitiesFeed(7)
          top = () => feed.data.value?.pages[0]?.[0]
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

    expect(top()).toMatchObject({ id: 22, city: 'Samora', mapThumbnailUrl: 'map' })
  })
})
