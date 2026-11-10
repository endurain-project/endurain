import type { Notification, NotificationDto } from '@/features/notifications/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/** Input for a notifications list request. */
export type NotificationsPage = {
  /** Opaque cursor from the previous slice; omit to start at the newest. */
  cursor?: string | null
  /** Slice size (records per request). */
  numRecords: number
}

/** One keyset slice of the notifications list. */
export type NotificationsSlice = {
  /** The notifications in this slice, newest first. */
  items: Notification[]
  /** Cursor for the following slice, or `null` on the last one. */
  nextCursor: string | null
}

/**
 * Maps a raw `NotificationRead` payload to the app's clean {@link Notification}
 * model. This is the single boundary where the backend wire format (snake_case,
 * nullable fields) is translated, so components never see the raw DTO.
 *
 * @param dto - Raw notification payload from the backend.
 * @returns The normalized notification model.
 */
export function mapNotification(dto: NotificationDto): Notification {
  const { id, read, created_at: createdAt, user_id: userId, ...typed } = dto
  return { id, read, createdAt, userId, ...typed }
}

/**
 * Fetches one keyset slice of the authenticated user's notifications.
 *
 * @param page - The cursor to resume after (none for the first slice) and the slice size.
 * @param signal - Optional abort signal so TanStack Query can cancel the
 *   request on unmount or invalidation.
 * @returns The slice's notifications, mapped to the clean model, and the next cursor.
 * @throws {HttpError} When the request fails.
 */
export async function fetchNotifications(
  { cursor, numRecords }: NotificationsPage,
  signal?: AbortSignal,
): Promise<NotificationsSlice> {
  const params = new URLSearchParams({ num_records: String(numRecords) })
  if (cursor) {
    params.set('cursor', cursor)
  }
  const result = await apiFetch<Schemas['NotificationPage']>(`/notifications?${params}`, {
    signal,
  })
  return { items: result.items.map(mapNotification), nextCursor: result.next_cursor ?? null }
}

/**
 * Fetches how many of the authenticated user's notifications are unread.
 *
 * @param signal - Optional abort signal so TanStack Query can cancel the
 *   request on unmount or invalidation.
 * @returns The number of unread notifications.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUnreadNotificationsCount(signal?: AbortSignal): Promise<number> {
  const result = await apiFetch<Schemas['NotificationUnreadCount']>('/notifications/unread-count', {
    signal,
  })
  return result.count
}

/**
 * Marks a single notification as read. The backend replies `204 No Content`, so
 * there is no response body to map.
 *
 * @param id - The notification id to mark as read.
 * @throws {HttpError} When the request fails.
 */
export async function markNotificationRead(id: number): Promise<void> {
  await apiFetch<void>(`/notifications/${id}/read`, {
    method: 'POST',
    responseType: 'void',
  })
}

/**
 * Marks every unread notification as read in a single request. The backend
 * replies `204 No Content`, so there is no response body to map.
 *
 * @throws {HttpError} When the request fails.
 */
export async function markAllNotificationsRead(): Promise<void> {
  await apiFetch<void>(`/notifications/read`, {
    method: 'POST',
    responseType: 'void',
  })
}
