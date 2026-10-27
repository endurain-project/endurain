import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import type { ComputedRef, Ref } from 'vue'

import {
  UNREAD_CONNECTED_POLL_INTERVAL_MS,
  UNREAD_POLL_INTERVAL_MS,
  useUnreadNotificationsCount,
} from '@/features/notifications/composables/useNotifications'
import { fetchUnreadNotificationsCount } from '@/features/notifications/services/notifications'
import { useRealtime } from '@/composables/useRealtime'

const useQuery = vi.fn<(options: Record<string, unknown>) => unknown>(() => ({}))

vi.mock('@tanstack/vue-query', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@tanstack/vue-query')>()),
  useQuery: (options: Record<string, unknown>) => useQuery(options),
}))

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

vi.mock('@/composables/useRealtime', async () => {
  const { ref: vueRef } = await import('vue')
  const status = vueRef<'idle' | 'connecting' | 'open' | 'closed'>('closed')
  return { useRealtime: () => ({ status }) }
})

vi.mock('@/features/notifications/services/notifications', () => ({
  fetchNotifications: vi.fn<() => Promise<never[]>>(() => Promise.resolve([])),
  fetchUnreadNotificationsCount: vi.fn<(signal?: AbortSignal) => Promise<number>>(() =>
    Promise.resolve(0),
  ),
  markAllNotificationsRead: vi.fn<() => Promise<void>>(),
  markNotificationRead: vi.fn<() => Promise<void>>(),
}))

describe('unread notifications polling', () => {
  const status = useRealtime().status as Ref<'idle' | 'connecting' | 'open' | 'closed'>

  beforeEach(() => {
    useQuery.mockClear()
    status.value = 'closed'
  })

  it('adapts the fallback interval to realtime connection state', () => {
    useUnreadNotificationsCount()

    const options = useQuery.mock.calls[0]?.[0] as { refetchInterval: ComputedRef<number | false> }
    expect(options.refetchInterval.value).toBe(UNREAD_POLL_INTERVAL_MS)
    expect(UNREAD_POLL_INTERVAL_MS).toBeGreaterThanOrEqual(30_000)

    status.value = 'open'
    expect(options.refetchInterval.value).toBe(UNREAD_CONNECTED_POLL_INTERVAL_MS)
    expect(UNREAD_CONNECTED_POLL_INTERVAL_MS).toBeGreaterThan(UNREAD_POLL_INTERVAL_MS)

    status.value = 'closed'
    expect(options.refetchInterval.value).toBe(UNREAD_POLL_INTERVAL_MS)
  })

  it('polls the server for the count instead of counting a page of rows itself', async () => {
    vi.mocked(fetchUnreadNotificationsCount).mockResolvedValueOnce(31)
    const signal = new AbortController().signal

    useUnreadNotificationsCount()
    const options = useQuery.mock.calls[0]?.[0] as {
      queryFn: (context: { signal: AbortSignal }) => Promise<number>
      select?: unknown
    }

    await expect(options.queryFn({ signal })).resolves.toBe(31)
    expect(fetchUnreadNotificationsCount).toHaveBeenCalledWith(signal)
    expect(options.select).toBeUndefined()
  })
})
