import {
  Activity,
  Bell,
  CopyCheck,
  KeyRound,
  LockKeyhole,
  LogIn,
  ShieldAlert,
  UserCheck,
  Trash2,
  Unplug,
  UserPlus,
  Watch,
  type LucideIcon,
} from '@lucide/vue'
import type { RouteLocationRaw } from 'vue-router'

import type { Notification } from '@/features/notifications/types'

import { formatMediumDate } from '@/utils/datetime'

/**
 * i18n key segment of each account-security change the backend reports in the
 * notification's `change` option. A change missing here renders the generic
 * message.
 */
const ACCOUNT_SECURITY_CHANGE_KEY: Record<string, string> = {
  password_changed: 'passwordChanged',
  password_reset: 'passwordReset',
  password_set_by_admin: 'passwordSetByAdmin',
  mfa_enabled: 'mfaEnabled',
  mfa_disabled: 'mfaDisabled',
  mfa_reset_by_admin: 'mfaResetByAdmin',
  password_change_required_by_admin: 'passwordChangeRequiredByAdmin',
  backup_codes_generated: 'backupCodesGenerated',
  api_key_created: 'apiKeyCreated',
  api_keys_revoked_by_admin: 'apiKeysRevokedByAdmin',
  identity_provider_unlinked: 'identityProviderUnlinked',
  account_locked: 'accountLocked',
  mfa_locked: 'mfaLocked',
  step_up_session_ended: 'stepUpSessionEnded',
  step_up_locked: 'stepUpLocked',
  backup_code_used: 'backupCodeUsed',
  refresh_token_reuse_detected: 'refreshTokenReuseDetected',
  role_changed_by_admin: 'roleChangedByAdmin',
  account_deactivated_by_admin: 'accountDeactivatedByAdmin',
  username_changed: 'usernameChanged',
}

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
  currentUserId?: string | null
  /** The viewer's locale, used to format dates a notification names. */
  locale?: string
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
  const base = 'notifications.types'

  switch (notification.type) {
    case 'new_activity': {
      return {
        icon: Activity,
        titleKey: `${base}.newActivity.title`,
        bodyKey: `${base}.newActivity.body`,
        to: { name: 'activity', params: { id: notification.options.activity_id } },
      }
    }
    case 'duplicate_activity': {
      return {
        icon: CopyCheck,
        titleKey: `${base}.duplicateActivity.title`,
        bodyKey: `${base}.duplicateActivity.body`,
        to: { name: 'activity', params: { id: notification.options.activity_id } },
      }
    }
    case 'new_follower_request': {
      const currentUserId = context.currentUserId
      return {
        icon: UserPlus,
        titleKey: `${base}.newFollowerRequest.title`,
        bodyKey: `${base}.newFollowerRequest.body`,
        bodyParams: {
          name: notification.options.user_name,
          username: notification.options.user_username,
        },
        // The request targets the viewer, so it deep-links to their own
        // followers list rather than the requester's profile.
        to:
          currentUserId == null
            ? null
            : { name: 'user', params: { id: currentUserId }, query: { tab: 'followers' } },
      }
    }
    case 'new_follower_request_accepted': {
      return {
        icon: UserCheck,
        titleKey: `${base}.followerRequestAccepted.title`,
        bodyKey: `${base}.followerRequestAccepted.body`,
        bodyParams: {
          name: notification.options.user_name,
          username: notification.options.user_username,
        },
        to: { name: 'user', params: { id: notification.options.user_id } },
      }
    }
    case 'garmin_token_expired': {
      return {
        icon: Watch,
        titleKey: `${base}.garminTokenExpired.title`,
        bodyKey: `${base}.garminTokenExpired.body`,
        to: { name: 'settings', query: { tab: 'integrations' } },
      }
    }
    case 'strava_token_expired': {
      // Only a revocation on Strava names the day the Strava data is deleted.
      const deleteOn = notification.options.delete_on ?? ''
      return {
        icon: Unplug,
        titleKey: `${base}.stravaTokenExpired.title`,
        bodyKey: deleteOn
          ? `${base}.stravaTokenExpired.bodyRevoked`
          : `${base}.stravaTokenExpired.body`,
        ...(deleteOn && {
          bodyParams: { date: formatMediumDate(deleteOn, context.locale, 'UTC') },
        }),
        to: { name: 'settings', query: { tab: 'integrations' } },
      }
    }
    case 'strava_data_deleted': {
      return {
        icon: Trash2,
        titleKey: `${base}.stravaDataDeleted.title`,
        bodyKey: `${base}.stravaDataDeleted.body`,
        to: { name: 'settings', query: { tab: 'integrations' } },
      }
    }
    case 'idp_linked': {
      const name = notification.options.idp_name ?? ''
      return {
        icon: KeyRound,
        titleKey: `${base}.idpLinked.title`,
        // A provider deleted since the link has no name, so the generic body applies.
        bodyKey: name ? `${base}.idpLinked.body` : `${base}.idpLinked.bodyGeneric`,
        bodyParams: { name },
        to: { name: 'settings-security' },
      }
    }
    case 'account_security_changed': {
      const changeKey = ACCOUNT_SECURITY_CHANGE_KEY[notification.options.change]
      const prefix = `${base}.accountSecurityChanged.${changeKey ?? 'unknown'}`
      const name = notification.options.idp_name ?? ''
      const remaining = notification.options.backup_codes_remaining ?? null
      const accessType = notification.options.access_type ?? null
      let bodyKey = `${prefix}.body`
      if (changeKey === 'identityProviderUnlinked' && !name) {
        // A provider deleted since the unlink has no name, so the generic body applies.
        bodyKey = `${prefix}.bodyGeneric`
      } else if (changeKey === 'backupCodeUsed' && remaining !== null) {
        bodyKey = remaining > 0 ? `${prefix}.bodyRemaining` : `${prefix}.bodyNone`
      } else if (changeKey === 'roleChangedByAdmin' && accessType === 'admin') {
        bodyKey = `${prefix}.bodyAdmin`
      } else if (changeKey === 'roleChangedByAdmin' && accessType === 'regular') {
        bodyKey = `${prefix}.bodyRegular`
      }
      return {
        icon: LockKeyhole,
        titleKey: `${prefix}.title`,
        bodyKey,
        bodyParams: { name, ...(remaining !== null && { count: String(remaining) }) },
        to: { name: 'settings-security' },
      }
    }
    case 'new_device_sign_in': {
      return {
        icon: LogIn,
        titleKey: `${base}.newDeviceSignIn.title`,
        bodyKey: `${base}.newDeviceSignIn.body`,
        bodyParams: {
          browser: notification.options.browser,
          os: notification.options.operating_system,
          ip: notification.options.ip_address,
        },
        to: { name: 'settings-security' },
      }
    }
    case 'admin_new_sign_up_approval_request': {
      return {
        icon: ShieldAlert,
        titleKey: `${base}.adminSignUpApproval.title`,
        bodyKey: `${base}.adminSignUpApproval.body`,
        bodyParams: {
          name: notification.options.user_name,
          username: notification.options.user_username,
        },
        to: { name: 'settings-user-detail', params: { id: notification.options.user_id } },
      }
    }
    case 'admin_user_promoted': {
      return {
        icon: ShieldAlert,
        titleKey: `${base}.adminUserPromoted.title`,
        bodyKey: `${base}.adminUserPromoted.body`,
        bodyParams: {
          name: notification.options.user_name,
          username: notification.options.user_username,
        },
        to: { name: 'settings-user-detail', params: { id: notification.options.user_id } },
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
