import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { storeToRefs } from 'pinia'
import {
  type InfiniteData,
  type QueryClient,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/vue-query'

import type { Notification } from '@/features/notifications/types'

import { queryKeys } from '@/services/queryKeys'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useRealtime } from '@/composables/useRealtime'
import {
  fetchNotifications,
  fetchUnreadNotificationsCount,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationsPage,
} from '@/features/notifications/services/notifications'

/** Default notifications page size when a caller doesn't specify one. */
const DEFAULT_PAGE_SIZE = 25

/** How often the unread badge polls while the realtime connection is unavailable. */
export const UNREAD_POLL_INTERVAL_MS = 60_000

/** Connected fallback for a realtime hint lost during a server-side channel gap. */
export const UNREAD_CONNECTED_POLL_INTERVAL_MS = 5 * 60_000

/**
 * Read path for the notifications list — the canonical server-state pattern:
 * a service function (`fetchNotifications`) + a key from the central
 * {@link queryKeys} factory, consumed through TanStack Query so callers inherit
 * caching, de-duplication, background refetch, and cancellation. The query is
 * gated on authentication so it never fires for a logged-out viewer, and on the
 * caller's `enabled` flag so a closed preview neither loads nor refetches on a
 * realtime push. It is always stale, so each time the flag turns on it refetches:
 * a push that was lost never leaves stale rows in front of the user.
 *
 * @param params - Optional reactive page/size; defaults to page 1.
 * @param enabled - Reactive gate (e.g. "the preview is open") ANDed with the auth gate.
 * @returns The TanStack Query result for the notifications page.
 */
export function useNotificationsQuery(
  params?: MaybeRefOrGetter<Partial<NotificationsPage>>,
  enabled: MaybeRefOrGetter<boolean> = true,
) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  const page = computed<NotificationsPage>(() => {
    const value = toValue(params)
    return {
      page: value?.page ?? 1,
      numRecords: value?.numRecords ?? DEFAULT_PAGE_SIZE,
    }
  })

  return useQuery<Notification[]>({
    queryKey: computed(() => queryKeys.notifications.list(page.value)),
    queryFn: ({ signal }) => fetchNotifications(page.value, signal),
    enabled: computed(() => toValue(enabled) && isAuthenticated.value),
    staleTime: 0,
  })
}

/**
 * Canonical paginated-list pattern: an infinite query that appends one page at
 * a time as the viewer scrolls. Copy this for every list view (activities,
 * gears, health). The query is keyed on the page size only — not the page
 * number — so all pages share one cache entry (`InfiniteData<Notification[]>`),
 * which is what lets {@link applyOptimisticRead} flip a single row across the
 * whole list. Gated on authentication so it never fires when logged out.
 *
 * @param pageSize - Records per page; also the key's only filter.
 * @returns The TanStack infinite-query result for the notifications list.
 */
export function useInfiniteNotificationsQuery(pageSize: number = DEFAULT_PAGE_SIZE) {
  const { isAuthenticated } = storeToRefs(useAuthStore())

  return useInfiniteQuery({
    queryKey: queryKeys.notifications.list({ numRecords: pageSize }),
    queryFn: ({ pageParam, signal }) =>
      fetchNotifications({ page: pageParam, numRecords: pageSize }, signal),
    initialPageParam: 1,
    // A short page means the server has no more rows, so stop paging; otherwise
    // request the next page number.
    getNextPageParam: (lastPage: Notification[], _allPages, lastPageParam: number) =>
      lastPage.length < pageSize ? undefined : lastPageParam + 1,
    enabled: isAuthenticated,
  })
}

/**
 * Unread-count query backing the navbar badge: the server counts the unread
 * notifications, so the badge is exact however many there are and only a number
 * crosses the wire.
 * Stored under {@link queryKeys.notifications.unreadCount} (outside the `list`
 * prefix) so the optimistic updater never touches it; notification hints and
 * mark-read mutations invalidate it for the authoritative count. It polls every
 * {@link UNREAD_POLL_INTERVAL_MS} while disconnected and every
 * {@link UNREAD_CONNECTED_POLL_INTERVAL_MS} while connected, covering hints lost
 * during a server-side channel gap.
 *
 * @returns A TanStack Query result whose `data` is the unread count.
 */
export function useUnreadNotificationsCount() {
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const { status } = useRealtime()

  return useQuery<number>({
    queryKey: queryKeys.notifications.unreadCount(),
    queryFn: ({ signal }) => fetchUnreadNotificationsCount(signal),
    enabled: isAuthenticated,
    refetchInterval: computed(() =>
      status.value === 'open' ? UNREAD_CONNECTED_POLL_INTERVAL_MS : UNREAD_POLL_INTERVAL_MS,
    ),
  })
}

/**
 * Either shape the notifications list cache can hold: a flat page (from
 * {@link useNotificationsQuery}) or an infinite query's accumulated pages (from
 * {@link useInfiniteNotificationsQuery}). The optimistic helpers handle both so
 * one mutation keeps every list view consistent.
 */
type CachedNotifications = Notification[] | InfiniteData<Notification[]>

/**
 * Returns a copy of a cached notifications value with the matching row marked
 * read, transparently handling both the flat-array and `InfiniteData` shapes.
 * Pure and immutable so it never mutates cached state in place.
 *
 * @param data - The cached value, or `undefined` for an unpopulated query.
 * @param id - The notification id to flip to read.
 * @returns The updated value, or `undefined` when there was nothing cached.
 */
function markNotificationReadInCache(
  data: CachedNotifications | undefined,
  id: number,
): CachedNotifications | undefined {
  if (!data) {
    return data
  }
  const flip = (item: Notification): Notification =>
    item.id === id ? { ...item, read: true } : item
  if (Array.isArray(data)) {
    return data.map(flip)
  }
  return { ...data, pages: data.pages.map((page) => page.map(flip)) }
}

/**
 * Returns a copy of a cached notifications value with every row marked read,
 * transparently handling both the flat-array and `InfiniteData` shapes. Pure
 * and immutable so it never mutates cached state in place.
 *
 * @param data - The cached value, or `undefined` for an unpopulated query.
 * @returns The updated value, or `undefined` when there was nothing cached.
 */
function markAllNotificationsReadInCache(
  data: CachedNotifications | undefined,
): CachedNotifications | undefined {
  if (!data) {
    return data
  }
  const flip = (item: Notification): Notification => (item.read ? item : { ...item, read: true })
  if (Array.isArray(data)) {
    return data.map(flip)
  }
  return { ...data, pages: data.pages.map((page) => page.map(flip)) }
}

/**
 * Snapshot of every cached notifications list, captured before an optimistic
 * update so it can be restored verbatim if the mutation fails.
 */
export type NotificationsSnapshot = [readonly unknown[], CachedNotifications | undefined][]

/**
 * Optimistically marks a notification read across every cached notifications
 * list, returning a snapshot for rollback. Exported as a pure function so the
 * cache mutation — the easy-to-get-wrong part — is unit-testable without
 * mounting a component. Works regardless of whether a list is cached as a flat
 * page or as infinite-query pages.
 *
 * @param client - The active query client.
 * @param id - The notification id being marked read.
 * @returns A snapshot of the lists as they were before the update.
 */
export function applyOptimisticRead(client: QueryClient, id: number): NotificationsSnapshot {
  const snapshot = client.getQueriesData<CachedNotifications>({
    queryKey: queryKeys.notifications.lists(),
  })
  client.setQueriesData<CachedNotifications>(
    { queryKey: queryKeys.notifications.lists() },
    (data) => markNotificationReadInCache(data, id),
  )
  return snapshot
}

/**
 * Optimistically marks every notification read across all cached lists,
 * returning a snapshot for rollback. Like {@link applyOptimisticRead} but flips
 * the whole list rather than a single row, backing the "mark all as read"
 * control. Exported as a pure function so the cache mutation is unit-testable
 * without mounting a component.
 *
 * @param client - The active query client.
 * @returns A snapshot of the lists as they were before the update.
 */
export function applyOptimisticReadAll(client: QueryClient): NotificationsSnapshot {
  const snapshot = client.getQueriesData<CachedNotifications>({
    queryKey: queryKeys.notifications.lists(),
  })
  client.setQueriesData<CachedNotifications>(
    { queryKey: queryKeys.notifications.lists() },
    (data) => markAllNotificationsReadInCache(data),
  )
  return snapshot
}

/**
 * Restores notification lists from a snapshot taken by {@link applyOptimisticRead}.
 *
 * @param client - The active query client.
 * @param snapshot - The snapshot to restore.
 */
export function restoreNotifications(client: QueryClient, snapshot: NotificationsSnapshot): void {
  for (const [key, data] of snapshot) {
    client.setQueryData(key, data)
  }
}

/**
 * Write path reference for the whole app — the canonical mutation pattern:
 *
 *   1. `onMutate`  — cancel in-flight reads, snapshot the cache, then apply the
 *      optimistic change so the UI updates instantly.
 *   2. `onError`   — roll the cache back to the snapshot.
 *   3. `onSettled` — invalidate the domain's broad key so the server's
 *      authoritative state replaces the optimistic guess.
 *
 * Copy this shape for activities, gears, goals, health, etc. Failures are
 * already routed to telemetry by the shared mutation cache, so this composable
 * stays focused on cache correctness and lets the view decide on toasts.
 *
 * @returns The TanStack Query mutation for marking a notification read.
 */
export function useMarkNotificationReadMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, number, NotificationsSnapshot>({
    mutationKey: queryKeys.notifications.all(),
    mutationFn: (id) => markNotificationRead(id),
    onMutate: async (id) => {
      // Cancel outgoing refetches so they can't clobber the optimistic update.
      await client.cancelQueries({ queryKey: queryKeys.notifications.lists() })
      return applyOptimisticRead(client, id)
    },
    onError: (_error, _id, snapshot) => {
      if (snapshot) {
        restoreNotifications(client, snapshot)
      }
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.notifications.all() })
    },
  })
}

/**
 * Bulk variant of {@link useMarkNotificationReadMutation}: marks every unread
 * notification read in one request, following the same optimistic
 * snapshot/rollback/invalidate shape. Backs the "mark all as read" button.
 *
 * @returns The TanStack Query mutation for marking all notifications read.
 */
export function useMarkAllNotificationsReadMutation() {
  const client = useQueryClient()

  return useMutation<void, Error, void, NotificationsSnapshot>({
    mutationKey: queryKeys.notifications.all(),
    mutationFn: () => markAllNotificationsRead(),
    onMutate: async () => {
      // Cancel outgoing refetches so they can't clobber the optimistic update.
      await client.cancelQueries({ queryKey: queryKeys.notifications.lists() })
      return applyOptimisticReadAll(client)
    },
    onError: (_error, _vars, snapshot) => {
      if (snapshot) {
        restoreNotifications(client, snapshot)
      }
    },
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.notifications.all() })
    },
  })
}
