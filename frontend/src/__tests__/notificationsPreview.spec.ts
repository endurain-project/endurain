import { defineComponent, h, ref, type Ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Notification } from '@/features/notifications/types'

import { useNotificationsQuery } from '@/features/notifications/composables/useNotifications'
import { fetchNotifications } from '@/features/notifications/services/notifications'
import { queryKeys } from '@/services/queryKeys'

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/features/notifications/services/notifications', () => ({
  fetchNotifications: vi.fn<() => Promise<Notification[]>>(() => Promise.resolve([])),
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
