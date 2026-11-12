import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { type InfiniteData, QueryClient } from '@tanstack/vue-query'

import type { Notification, NotificationDto } from '@/features/notifications/types'
import type { NotificationsSlice } from '@/features/notifications/services/notifications'

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
import { activityUuid } from './fixtures/activity'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Builds a stable UUID from a small number so ids stay readable in assertions. */
function uuidOf(n: number): string {
  return `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
}

const dto: NotificationDto = {
  id: uuidOf(7),
  type: 'new_activity',
  read: false,
  options: { activity_id: activityUuid(42) },
  created_at: '2026-06-19T10:00:00Z',
  user_id: 1,
}

function notification(overrides: { id?: string; read?: boolean } = {}): Notification {
  return {
    id: uuidOf(7),
    type: 'new_activity',
    read: false,
    options: { activity_id: activityUuid(42) },
    createdAt: '2026-06-19T10:00:00Z',
    userId: 1,
    ...overrides,
  }
}

describe('mapNotification', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapNotification(dto)).toEqual(notification())
  })
})

describe('notification service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the first slice without a cursor and maps the result', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [dto], num_records: 10, next_cursor: 'c1' })

    const result = await fetchNotifications({ numRecords: 10 })

    expect(apiFetch).toHaveBeenCalledWith(
      '/notifications?num_records=10',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual({ items: [notification()], nextCursor: 'c1' })
  })

  it('sends the cursor of the previous slice to request the next one', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], num_records: 10, next_cursor: null })

    await fetchNotifications({ cursor: 'a+b/c=', numRecords: 10 })

    expect(apiFetch).toHaveBeenCalledWith(
      '/notifications?num_records=10&cursor=a%2Bb%2Fc%3D',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('reads the unread count from the unread-count route', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ count: 42 })
    const signal = new AbortController().signal

    await expect(fetchUnreadNotificationsCount(signal)).resolves.toBe(42)

    expect(apiFetch).toHaveBeenCalledWith('/notifications/unread-count', { signal })
  })

  it('maps an empty slice to no notifications and no next cursor', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [], num_records: 25, next_cursor: null })
    await expect(fetchNotifications({ numRecords: 25 })).resolves.toEqual({
      items: [],
      nextCursor: null,
    })
  })

  it('marks a notification read via a void POST', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await markNotificationRead(uuidOf(7))

    expect(apiFetch).toHaveBeenCalledWith(`/notifications/${uuidOf(7)}/read`, {
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
    const listKey = queryKeys.notifications.list({ numRecords: 6 })
    const otherKey = queryKeys.notifications.list({ page: 2, numRecords: 25 })
    client.setQueryData(listKey, [notification({ id: uuidOf(7) }), notification({ id: uuidOf(8) })])
    client.setQueryData(otherKey, [notification({ id: uuidOf(7) })])

    const snapshot = applyOptimisticRead(client, uuidOf(7))

    expect(client.getQueryData<Notification[]>(listKey)).toEqual([
      notification({ id: uuidOf(7), read: true }),
      notification({ id: uuidOf(8) }),
    ])
    expect(client.getQueryData<Notification[]>(otherKey)).toEqual([
      notification({ id: uuidOf(7), read: true }),
    ])
    // The snapshot captured the lists before the optimistic flip.
    expect(snapshot).toHaveLength(2)
  })

  it('restores the exact prior state on rollback', () => {
    const listKey = queryKeys.notifications.list({ numRecords: 6 })
    const original = [notification({ id: uuidOf(7) }), notification({ id: uuidOf(8) })]
    client.setQueryData(listKey, original)

    const snapshot = applyOptimisticRead(client, uuidOf(7))
    restoreNotifications(client, snapshot)

    expect(client.getQueryData<Notification[]>(listKey)).toEqual(original)
  })

  it('flips read inside an infinite-query cache shape', () => {
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    client.setQueryData<InfiniteData<NotificationsSlice>>(infiniteKey, {
      pages: [
        {
          items: [notification({ id: uuidOf(7) }), notification({ id: uuidOf(8) })],
          nextCursor: 'c1',
        },
        { items: [notification({ id: uuidOf(9) })], nextCursor: null },
      ],
      pageParams: [null, 'c1'],
    })

    applyOptimisticRead(client, uuidOf(8))

    expect(client.getQueryData<InfiniteData<NotificationsSlice>>(infiniteKey)).toEqual({
      pages: [
        {
          items: [notification({ id: uuidOf(7) }), notification({ id: uuidOf(8), read: true })],
          nextCursor: 'c1',
        },
        { items: [notification({ id: uuidOf(9) })], nextCursor: null },
      ],
      pageParams: [null, 'c1'],
    })
  })

  it('restores an infinite-query snapshot on rollback', () => {
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    const original: InfiniteData<NotificationsSlice> = {
      pages: [{ items: [notification({ id: uuidOf(7) })], nextCursor: null }],
      pageParams: [null],
    }
    client.setQueryData(infiniteKey, original)

    const snapshot = applyOptimisticRead(client, uuidOf(7))
    restoreNotifications(client, snapshot)

    expect(client.getQueryData<InfiniteData<NotificationsSlice>>(infiniteKey)).toEqual(original)
  })

  it('flips every row read across all cached lists when marking all read', () => {
    const listKey = queryKeys.notifications.list({ numRecords: 6 })
    const infiniteKey = queryKeys.notifications.list({ numRecords: 25 })
    client.setQueryData(listKey, [
      notification({ id: uuidOf(7) }),
      notification({ id: uuidOf(8), read: true }),
    ])
    client.setQueryData<InfiniteData<NotificationsSlice>>(infiniteKey, {
      pages: [
        { items: [notification({ id: uuidOf(9) })], nextCursor: 'c1' },
        { items: [notification({ id: uuidOf(10) })], nextCursor: null },
      ],
      pageParams: [null, 'c1'],
    })

    const snapshot = applyOptimisticReadAll(client)

    expect(client.getQueryData<Notification[]>(listKey)).toEqual([
      notification({ id: uuidOf(7), read: true }),
      notification({ id: uuidOf(8), read: true }),
    ])
    expect(client.getQueryData<InfiniteData<NotificationsSlice>>(infiniteKey)).toEqual({
      pages: [
        { items: [notification({ id: uuidOf(9), read: true })], nextCursor: 'c1' },
        { items: [notification({ id: uuidOf(10), read: true })], nextCursor: null },
      ],
      pageParams: [null, 'c1'],
    })
    expect(snapshot).toHaveLength(2)
  })
})
