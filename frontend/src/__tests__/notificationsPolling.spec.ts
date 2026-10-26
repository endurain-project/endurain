import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import {
  UNREAD_POLL_INTERVAL_MS,
  useUnreadNotificationsCount,
} from '@/features/notifications/composables/useNotifications'
import { fetchUnreadNotificationsCount } from '@/features/notifications/services/notifications'

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

vi.mock('@/features/notifications/services/notifications', () => ({
  fetchNotifications: vi.fn<() => Promise<never[]>>(() => Promise.resolve([])),
  fetchUnreadNotificationsCount: vi.fn<(signal?: AbortSignal) => Promise<number>>(() =>
    Promise.resolve(0),
  ),
  markAllNotificationsRead: vi.fn<() => Promise<void>>(),
  markNotificationRead: vi.fn<() => Promise<void>>(),
}))

describe('unread notifications polling', () => {
  beforeEach(() => {
    useQuery.mockClear()
  })

  it('re-checks the server on a slow interval so a lost push self-heals', () => {
    useUnreadNotificationsCount()

    expect(useQuery.mock.calls[0]?.[0]).toMatchObject({ refetchInterval: UNREAD_POLL_INTERVAL_MS })
    expect(UNREAD_POLL_INTERVAL_MS).toBeGreaterThanOrEqual(30_000)
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
