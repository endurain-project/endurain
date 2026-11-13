import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { type InfiniteData, QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Notification } from '@/features/notifications/types'
import type { NotificationsSlice } from '@/features/notifications/services/notifications'

import i18n from '@/i18n'
import { HttpError, apiFetch } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import NotificationItem from '@/features/notifications/components/NotificationItem.vue'
import { useDeleteNotificationMutation } from '@/features/notifications/composables/useNotifications'
import {
  deleteNotification,
  fetchNotifications,
} from '@/features/notifications/services/notifications'
import { activityUuid, userUuid } from './fixtures/activity'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

vi.mock('@/features/notifications/services/notifications', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/notifications/services/notifications')>()),
  fetchNotifications: vi.fn<typeof fetchNotifications>(),
}))

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

const push = vi.fn<(to: unknown) => void>()

vi.mock('vue-router', () => ({
  useRouter: () => ({ hasRoute: () => true, push }),
  RouterLink: {
    props: ['to'],
    template: '<a data-test="link" @click="$router_push"><slot /></a>',
    methods: {
      $router_push() {
        push('navigated')
      },
    },
  },
}))

/** Builds a stable UUID from a small number so ids stay readable in assertions. */
function uuidOf(n: number): string {
  return `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
}

function notification(id: string, read = false): Notification {
  return {
    id,
    type: 'new_activity',
    read,
    options: { activity_id: activityUuid(42) },
    createdAt: '2026-06-19T10:00:00Z',
    userId: userUuid(1),
  }
}

describe('deleteNotification', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends a void DELETE to the notification', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteNotification(uuidOf(7))

    expect(apiFetch).toHaveBeenCalledWith(`/notifications/${uuidOf(7)}`, {
      method: 'DELETE',
      responseType: 'void',
    })
  })
})

describe('useDeleteNotificationMutation', () => {
  let client: QueryClient

  beforeEach(() => {
    vi.clearAllMocks()
    client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  })

  afterEach(() => client.clear())

  function mountMutation() {
    let mutation!: ReturnType<typeof useDeleteNotificationMutation>
    mount(
      defineComponent({
        setup() {
          mutation = useDeleteNotificationMutation()
          return () => h('div')
        },
      }),
      { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } },
    )
    return mutation
  }

  it('drops the row from the cached list and refreshes the list and the unread count', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)
    const listKey = queryKeys.notifications.list({ numRecords: 25 })
    client.setQueryData<InfiniteData<NotificationsSlice>>(listKey, {
      pages: [{ items: [notification(uuidOf(7)), notification(uuidOf(8))], nextCursor: null }],
      pageParams: [null],
    })
    client.setQueryData(queryKeys.notifications.unreadCount(), 2)
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const mutation = mountMutation()
    mutation.mutate(uuidOf(7))
    await flushPromises()

    expect(client.getQueryData<InfiniteData<NotificationsSlice>>(listKey)?.pages[0]?.items).toEqual(
      [notification(uuidOf(8))],
    )
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.notifications.all() })
    expect(client.getQueryState(queryKeys.notifications.unreadCount())?.isInvalidated).toBe(true)
  })

  it('treats an already gone notification as deleted and still refreshes', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(404, 'Not Found', null, 'urn:endurain:error:not-found'),
    )
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const mutation = mountMutation()
    mutation.mutate(uuidOf(7))
    await flushPromises()

    expect(mutation.isError.value).toBe(false)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.notifications.all() })
  })

  it('restores the list and surfaces any other failure', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(500, 'Server Error', null, 'urn:endurain:error:internal'),
    )
    const listKey = queryKeys.notifications.list({ numRecords: 25 })
    const original: InfiniteData<NotificationsSlice> = {
      pages: [{ items: [notification(uuidOf(7))], nextCursor: null }],
      pageParams: [null],
    }
    client.setQueryData(listKey, original)

    const mutation = mountMutation()
    mutation.mutate(uuidOf(7))
    await flushPromises()

    expect(mutation.isError.value).toBe(true)
    expect(client.getQueryData(listKey)).toEqual(original)
  })
})

describe('NotificationItem dismiss button', () => {
  it('emits dismiss with the id and does not mark read or navigate', async () => {
    const wrapper = mount(NotificationItem, {
      props: { notification: notification(uuidOf(7)) },
      global: { plugins: [i18n] },
    })

    await wrapper.get('button[data-testid="notification-dismiss"]').trigger('click')

    expect(wrapper.emitted('dismiss')).toEqual([[uuidOf(7)]])
    expect(wrapper.emitted('markRead')).toBeUndefined()
    expect(push).not.toHaveBeenCalled()
  })

  it('labels the button for assistive technology', () => {
    const wrapper = mount(NotificationItem, {
      props: { notification: notification(uuidOf(7), true) },
      global: { plugins: [i18n] },
    })

    expect(wrapper.get('button[data-testid="notification-dismiss"]').attributes('aria-label')).toBe(
      i18n.global.t('notifications.dismiss'),
    )
  })
})
