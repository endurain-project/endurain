import { defineComponent, h, ref, type Ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useInfiniteNotificationsQuery,
  useNotificationsQuery,
} from '@/features/notifications/composables/useNotifications'
import {
  fetchNotifications,
  type NotificationsSlice,
} from '@/features/notifications/services/notifications'
import { queryKeys } from '@/services/queryKeys'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/notifications/services/notifications', () => ({
  fetchNotifications: vi.fn<() => Promise<NotificationsSlice>>(() =>
    Promise.resolve({ items: [], nextCursor: null }),
  ),
  markAllNotificationsRead: vi.fn<() => Promise<void>>(),
  markNotificationRead: vi.fn<() => Promise<void>>(),
}))

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

/** Mounts the preview query behind the given `enabled` gate (the menu's open state). */
function mountPreview(queryClient: QueryClient, open: Ref<boolean>): void {
  wrapper = mount(
    defineComponent({
      setup() {
        useNotificationsQuery(() => ({ numRecords: 6 }), open)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
}

describe('notifications preview query gating', () => {
  it('does not fetch while the menu is closed, and fetches once it opens', async () => {
    const open = ref(false)
    mountPreview(new QueryClient(), open)
    await flushPromises()
    expect(fetchNotifications).not.toHaveBeenCalled()

    open.value = true
    await flushPromises()

    expect(fetchNotifications).toHaveBeenCalledTimes(1)
  })

  it('refetches each time the menu opens, so a lost push never leaves stale rows', async () => {
    const open = ref(true)
    mountPreview(new QueryClient(), open)
    await flushPromises()
    expect(fetchNotifications).toHaveBeenCalledTimes(1)

    open.value = false
    await flushPromises()
    open.value = true
    await flushPromises()

    expect(fetchNotifications).toHaveBeenCalledTimes(2)
  })

  it('leaves a realtime invalidation for the next open instead of refetching a closed menu', async () => {
    const queryClient = new QueryClient()
    const open = ref(true)
    mountPreview(queryClient, open)
    await flushPromises()
    open.value = false
    await flushPromises()
    vi.mocked(fetchNotifications).mockClear()

    await queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all() })
    await flushPromises()
    expect(fetchNotifications).not.toHaveBeenCalled()

    open.value = true
    await flushPromises()
    expect(fetchNotifications).toHaveBeenCalledTimes(1)
  })
})

describe('notifications infinite query', () => {
  it('requests the second slice with the cursor of the first', async () => {
    vi.mocked(fetchNotifications)
      .mockResolvedValueOnce({ items: [], nextCursor: 'cursor-1' })
      .mockResolvedValueOnce({ items: [], nextCursor: null })
    let query!: ReturnType<typeof useInfiniteNotificationsQuery>
    wrapper = mount(
      defineComponent({
        setup() {
          query = useInfiniteNotificationsQuery(10)
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]] } },
    )
    await flushPromises()

    expect(fetchNotifications).toHaveBeenNthCalledWith(
      1,
      { cursor: null, numRecords: 10 },
      expect.anything(),
    )
    expect(query.hasNextPage.value).toBe(true)

    await query.fetchNextPage()

    expect(fetchNotifications).toHaveBeenNthCalledWith(
      2,
      { cursor: 'cursor-1', numRecords: 10 },
      expect.anything(),
    )
    expect(query.hasNextPage.value).toBe(false)
  })
})
