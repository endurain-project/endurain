import {
  Activity,
  Bell,
  CopyCheck,
  KeyRound,
  ShieldAlert,
  UserCheck,
  Unplug,
  UserPlus,
  Watch,
  type LucideIcon,
} from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'

import type { Notification } from '@/features/notifications/types'

/**
 * Numeric notification types, mirroring the backend `NotificationType`
 * enum (`backend/app/notifications/constants.py`). Kept as a local constant so
 * the presenter reads by name instead of magic numbers; the wire contract is
 * the integer, so these must stay in sync with the backend.
 */
const NOTIFICATION_TYPE = {
  NEW_ACTIVITY: 1,
  DUPLICATE_ACTIVITY: 2,
  NEW_FOLLOWER_REQUEST: 11,
  NEW_FOLLOWER_REQUEST_ACCEPTED: 12,
  GARMIN_TOKEN_EXPIRED: 21,
  STRAVA_TOKEN_EXPIRED: 22,
  IDP_LINKED: 31,
  ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST: 101,
} as const

/**
 * Everything a notification row needs to render, derived purely from the
 * notification model. Keeping this a plain data object (icon component + i18n
 * keys + an optional route) means the mapping is unit-testable without mounting
 * a component, and the row stays a dumb presenter.
 *
 * @property icon - Lucide icon component representing the notification kind.
 * @property titleKey - i18n key for the bold headline.
 * @property bodyKey - i18n key for the supporting line.
 * @property bodyParams - Interpolation values for `bodyKey` (e.g. a username).
 * @property to - The intended navigation target, or `null` when the
 *   notification is not navigable. The target is emitted aspirationally even
 *   for routes that do not exist yet; the row guards it against the router so
 *   links light up automatically once those routes land.
 */
export interface NotificationPresentation {
  icon: LucideIcon
  titleKey: string
  bodyKey: string
  bodyParams?: Record<string, string>
  to: RouteLocationRaw | null
}

/** Optional rendering context the presenter can't infer from the model alone. */
export interface NotificationPresenterContext {
  /** The viewing user's id, used to deep-link follower requests to their list. */
  currentUserId?: number | null
}

/**
 * Reads a string field from a notification's loosely-typed `options` bag.
 *
 * @param options - The per-type metadata bag, possibly `null`.
 * @param key - The field to read.
 * @returns The string value, or an empty string when absent or not a string.
 */
function readString(options: Record<string, unknown> | null, key: string): string {
  const value = options?.[key]
  return typeof value === 'string' ? value : ''
}

/**
 * Reads a numeric field from a notification's loosely-typed `options` bag.
 *
 * @param options - The per-type metadata bag, possibly `null`.
 * @param key - The field to read.
 * @returns The numeric value, or `null` when absent or not a number.
 */
function readNumber(options: Record<string, unknown> | null, key: string): number | null {
  const value = options?.[key]
  return typeof value === 'number' ? value : null
}

/**
 * Maps a notification to its presentational shape: icon, localized message
 * keys, and an intended navigation target. Unknown or untyped notifications
 * degrade to a neutral "bell" fallback so a new backend type never renders
 * blank.
 *
 * @param notification - The notification to present.
 * @param context - Optional rendering context (e.g. the current user's id).
 * @returns The presentation model for the notification.
 */
export function presentNotification(
  notification: Notification,
  context: NotificationPresenterContext = {},
): NotificationPresentation {
  const { options } = notification
  const base = 'notifications.types'

  switch (notification.type) {
    case NOTIFICATION_TYPE.NEW_ACTIVITY: {
      const activityId = readNumber(options, 'activity_id')
      return {
        icon: Activity,
        titleKey: `${base}.newActivity.title`,
        bodyKey: `${base}.newActivity.body`,
        to: activityId === null ? null : { name: 'activity', params: { id: String(activityId) } },
      }
    }
    case NOTIFICATION_TYPE.DUPLICATE_ACTIVITY: {
      const activityId = readNumber(options, 'activity_id')
      return {
        icon: CopyCheck,
        titleKey: `${base}.duplicateActivity.title`,
        bodyKey: `${base}.duplicateActivity.body`,
        to: activityId === null ? null : { name: 'activity', params: { id: String(activityId) } },
      }
    }
    case NOTIFICATION_TYPE.NEW_FOLLOWER_REQUEST: {
      const currentUserId = context.currentUserId
      return {
        icon: UserPlus,
        titleKey: `${base}.newFollowerRequest.title`,
        bodyKey: `${base}.newFollowerRequest.body`,
        bodyParams: {
          name: readString(options, 'user_name'),
          username: readString(options, 'user_username'),
        },
        // The request targets the viewer, so it deep-links to their own
        // followers list rather than the requester's profile.
        to:
          currentUserId == null
            ? null
            : { name: 'user', params: { id: String(currentUserId) }, query: { tab: 'followers' } },
      }
    }
    case NOTIFICATION_TYPE.NEW_FOLLOWER_REQUEST_ACCEPTED: {
      const userId = readNumber(options, 'user_id')
      return {
        icon: UserCheck,
        titleKey: `${base}.followerRequestAccepted.title`,
        bodyKey: `${base}.followerRequestAccepted.body`,
        bodyParams: {
          name: readString(options, 'user_name'),
          username: readString(options, 'user_username'),
        },
        to: userId === null ? null : { name: 'user', params: { id: String(userId) } },
      }
    }
    case NOTIFICATION_TYPE.GARMIN_TOKEN_EXPIRED: {
      return {
        icon: Watch,
        titleKey: `${base}.garminTokenExpired.title`,
        bodyKey: `${base}.garminTokenExpired.body`,
        to: { name: 'settings', query: { tab: 'integrations' } },
      }
    }
    case NOTIFICATION_TYPE.STRAVA_TOKEN_EXPIRED: {
      return {
        icon: Unplug,
        titleKey: `${base}.stravaTokenExpired.title`,
        bodyKey: `${base}.stravaTokenExpired.body`,
        to: { name: 'settings', query: { tab: 'integrations' } },
      }
    }
    case NOTIFICATION_TYPE.IDP_LINKED: {
      const name = readString(options, 'idp_name')
      return {
        icon: KeyRound,
        titleKey: `${base}.idpLinked.title`,
        // A provider deleted since the link has no name, so the generic body applies.
        bodyKey: name ? `${base}.idpLinked.body` : `${base}.idpLinked.bodyGeneric`,
        bodyParams: { name },
        to: { name: 'settings-security' },
      }
    }
    case NOTIFICATION_TYPE.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST: {
      const userId = readNumber(options, 'user_id')
      return {
        icon: ShieldAlert,
        titleKey: `${base}.adminSignUpApproval.title`,
        bodyKey: `${base}.adminSignUpApproval.body`,
        bodyParams: {
          name: readString(options, 'user_name'),
          username: readString(options, 'user_username'),
        },
        to:
          userId === null
            ? { name: 'settings-users' }
            : { name: 'settings-user-detail', params: { id: String(userId) } },
      }
    }
    default:
      return {
        icon: Bell,
        titleKey: `${base}.unknown.title`,
        bodyKey: `${base}.unknown.body`,
        to: null,
      }
  }
}
