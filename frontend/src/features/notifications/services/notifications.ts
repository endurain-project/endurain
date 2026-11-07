import type { Notification, NotificationDto } from '@/features/notifications/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/** Pagination input for a notifications list request. */
export type NotificationsPage = {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
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
  return { id, read, createdAt: createdAt ?? null, userId, ...typed }
}

/**
 * Fetches one page of the authenticated user's notifications.
 *
 * @param page - The page number and size to fetch.
 * @param signal - Optional abort signal so TanStack Query can cancel the
 *   request on unmount or invalidation.
 * @returns The page's notifications, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchNotifications(
  { page, numRecords }: NotificationsPage,
  signal?: AbortSignal,
): Promise<Notification[]> {
  const result = await apiFetch<Schemas['NotificationPage']>(
    `/notifications?page_number=${page}&num_records=${numRecords}`,
    { signal },
  )
  return result.items.map(mapNotification)
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
