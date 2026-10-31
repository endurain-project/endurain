import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type InfiniteData, QueryClient } from '@tanstack/vue-query'

import type { Notification, NotificationDto } from '@/features/notifications/types'

import { apiFetch } from '@/services/http'
import {
  fetchNotifications,
  fetchUnreadNotificationsCount,
  mapNotification,
  markAllNotificationsRead,
  markNotificationRead,
} from '@/features/notifications/services/notifications'
import { queryKeys } from '@/services/queryKeys'
import {
  applyOptimisticRead,
  applyOptimisticReadAll,
  restoreNotifications,
} from '@/features/notifications/composables/useNotifications'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const dto: NotificationDto = {
  id: 7,
  type: 3,
  read: false,
  options: { activity_id: 42 },
  created_at: '2026-06-19T10:00:00Z',
  user_id: 1,
}

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: 7,
    type: 3,
    read: false,
    options: { activity_id: 42 },
    createdAt: '2026-06-19T10:00:00Z',
    userId: 1,
    ...overrides,
  }
}

describe('mapNotification', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapNotification(dto)).toEqual(notification())
  })

  it('coerces absent optional fields to null', () => {
    expect(mapNotification({ id: 1, type: 1, read: true, user_id: 9 })).toEqual({
      id: 1,
      type: 1,
      read: true,
      options: null,
      createdAt: null,
      userId: 9,
    })
  })
})

describe('notification service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the paginated notifications path and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [dto],
      total: 1,
      page: 2,
      num_records: 10,
      next: null,
    })

    const result = await fetchNotifications({ page: 2, numRecords: 10 })

    expect(apiFetch).toHaveBeenCalledWith(
      '/notifications?page_number=2&num_records=10',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual([notification()])
  })

  it('reads the unread count from the page total, without downloading any notification', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [dto],
      total: 42,
      page: 1,
      num_records: 1,
      next: 2,
    })
    const signal = new AbortController().signal

    await expect(fetchUnreadNotificationsCount(signal)).resolves.toBe(42)

    expect(apiFetch).toHaveBeenCalledWith('/notifications?unread_only=true&num_records=1', {
      signal,
    })
  })

  it('maps an empty page to no notifications', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      num_records: 25,
      next: null,
    })
    await expect(fetchNotifications({ page: 1, numRecords: 25 })).resolves.toEqual([])
  })

  it('marks a notification read via a void POST', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await markNotificationRead(7)

    expect(apiFetch).toHaveBeenCalledWith('/notifications/7/read', {
      method: 'POST',
      responseType: 'void',
    })
  })

  it('marks all notifications read via a void POST', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await markAllNotificationsRead()

    expect(apiFetch).toHaveBeenCalledWith('/notifications/read', {
      method: 'POST',
      responseType: 'void',
    })
  })
})

describe('optimistic read cache helpers', () => {
  let client: QueryClient

  beforeEach(() => {
    client = new QueryClient()
  })

  afterEach(() => {
    client.clear()
  })

  it('flips read to true across every cached list and snapshots the prior state', () => {
    const listKey = queryKeys.notifications.list({ page: 1, numRecords: 25 })
    const otherKey = queryKeys.notifications.list({ page: 2, numRecords: 25 })
    client.setQueryData(listKey, [notification({ id: 7 }), notification({ id: 8 })])
    client.setQueryData(otherKey, [notification({ id: 7 })])

    const snapshot = applyOptimisticRead(client, 7)

    expect(client.getQueryData<Notification[]>(listKey)).toEqual([
      notification({ id: 7, read: true }),
      notification({ id: 8 }),
    ])
    expect(client.getQueryData<Notification[]>(otherKey)).toEqual([
      notification({ id: 7, read: true }),
    ])
    // The snapshot captured the lists before the optimistic flip.
    expect(snapshot).toHaveLength(2)
  })

  it('restores the exact prior state on rollback', () => {
    const listKey = queryKeys.notifications.list({ page: 1, numRecords: 25 })
    const original = [notification({ id: 7 }), notification({ id: 8 })]
    client.setQueryData(listKey, original)

    const snapshot = applyOptimisticRead(client, 7)
    restoreNotifications(client, snapshot)

    expect(client.getQueryData<Notification[]>(listKey)).toEqual(original)
  })

  it('flips read inside an infinite-query cache shape', () => {
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    client.setQueryData<InfiniteData<Notification[]>>(infiniteKey, {
      pages: [[notification({ id: 7 }), notification({ id: 8 })], [notification({ id: 9 })]],
      pageParams: [1, 2],
    })

    applyOptimisticRead(client, 8)

    expect(client.getQueryData<InfiniteData<Notification[]>>(infiniteKey)).toEqual({
      pages: [
        [notification({ id: 7 }), notification({ id: 8, read: true })],
        [notification({ id: 9 })],
      ],
      pageParams: [1, 2],
    })
  })

  it('restores an infinite-query snapshot on rollback', () => {
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    const original: InfiniteData<Notification[]> = {
      pages: [[notification({ id: 7 })]],
      pageParams: [1],
    }
    client.setQueryData(infiniteKey, original)

    const snapshot = applyOptimisticRead(client, 7)
    restoreNotifications(client, snapshot)

    expect(client.getQueryData<InfiniteData<Notification[]>>(infiniteKey)).toEqual(original)
  })

  it('flips every row read across all cached lists when marking all read', () => {
    const listKey = queryKeys.notifications.list({ page: 1, numRecords: 25 })
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    client.setQueryData(listKey, [notification({ id: 7 }), notification({ id: 8, read: true })])
    client.setQueryData<InfiniteData<Notification[]>>(infiniteKey, {
      pages: [[notification({ id: 9 })], [notification({ id: 10 })]],
      pageParams: [1, 2],
    })

    const snapshot = applyOptimisticReadAll(client)

    expect(client.getQueryData<Notification[]>(listKey)).toEqual([
      notification({ id: 7, read: true }),
      notification({ id: 8, read: true }),
    ])
    expect(client.getQueryData<InfiniteData<Notification[]>>(infiniteKey)).toEqual({
      pages: [[notification({ id: 9, read: true })], [notification({ id: 10, read: true })]],
      pageParams: [1, 2],
    })
    expect(snapshot).toHaveLength(2)
  })
})
