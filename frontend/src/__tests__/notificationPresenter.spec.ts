import { describe, expect, it } from 'vitest'
import {
  Activity,
  Bell,
  CopyCheck,
  KeyRound,
  LockKeyhole,
  LogIn,
  ShieldAlert,
  UserCheck,
  UserPlus,
  Unplug,
  Watch,
} from '@lucide/vue'

import i18n from '@/i18n'
import type {
  Notification,
  NotificationOptionsOf,
  NotificationType,
} from '@/features/notifications/types'

import { presentNotification } from '@/features/notifications/utils/notificationPresenter'

/**
 * Builds a notification with sensible defaults so each test only states the
 * fields it cares about. The caller states the options of the type it names.
 *
 * @param type - The notification type.
 * @param options - The options that type stores.
 * @returns A notification model for the presenter.
 */
function make<Type extends NotificationType>(
  type: Type,
  options: NotificationOptionsOf<Type>,
): Notification {
  return { id: 1, type, read: false, options, createdAt: null, userId: 5 } as Notification
}

const USER = { user_id: 3, user_name: 'Ada', user_username: 'ada' }
const NO_OPTIONS = {}

describe('presentNotification', () => {
  it('presents a new-activity notification with a deep link', () => {
    const result = presentNotification(make('new_activity', { activity_id: 42 }))

    expect(result.icon).toBe(Activity)
    expect(result.titleKey).toBe('notifications.types.newActivity.title')
    expect(result.bodyKey).toBe('notifications.types.newActivity.body')
    expect(result.to).toEqual({ name: 'activity', params: { id: '42' } })
  })

  it('presents a duplicate-activity notification', () => {
    const result = presentNotification(make('duplicate_activity', { activity_id: 7 }))

    expect(result.icon).toBe(CopyCheck)
    expect(result.titleKey).toBe('notifications.types.duplicateActivity.title')
    expect(result.to).toEqual({ name: 'activity', params: { id: '7' } })
  })

  it('links a follower request to the viewer followers list', () => {
    const result = presentNotification(make('new_follower_request', USER), {
      currentUserId: 9,
    })

    expect(result.icon).toBe(UserPlus)
    expect(result.bodyParams).toEqual({ name: 'Ada', username: 'ada' })
    expect(result.to).toEqual({ name: 'user', params: { id: '9' }, query: { tab: 'followers' } })
  })

  it('omits the follower-request link without a current user id', () => {
    expect(presentNotification(make('new_follower_request', USER)).to).toBeNull()
  })

  it('links an accepted follower request to that user', () => {
    const result = presentNotification(make('new_follower_request_accepted', USER))

    expect(result.icon).toBe(UserCheck)
    expect(result.to).toEqual({ name: 'user', params: { id: '3' } })
  })

  it('routes a Garmin token expiry to settings integrations', () => {
    const result = presentNotification(make('garmin_token_expired', NO_OPTIONS))

    expect(result.icon).toBe(Watch)
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('routes a Strava token expiry to settings integrations', () => {
    const result = presentNotification(make('strava_token_expired', NO_OPTIONS))

    expect(result.icon).toBe(Unplug)
    expect(result.titleKey).toBe('notifications.types.stravaTokenExpired.title')
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('names the day the Strava data is deleted when access was revoked on Strava', () => {
    const result = presentNotification(make('strava_token_expired', { delete_on: '2026-11-12' }), {
      locale: 'en',
    })

    expect(result.titleKey).toBe('notifications.types.stravaTokenExpired.title')
    expect(result.bodyKey).toBe('notifications.types.stravaTokenExpired.bodyRevoked')
    expect(result.bodyParams).toEqual({ date: 'Nov 12, 2026' })
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('keeps the plain Strava message when no deletion day is named', () => {
    const result = presentNotification(make('strava_token_expired', NO_OPTIONS))

    expect(result.bodyKey).toBe('notifications.types.stravaTokenExpired.body')
    expect(result.bodyParams).toBeUndefined()
  })

  it('tells the user their Strava data was deleted', () => {
    const result = presentNotification(make('strava_data_deleted', NO_OPTIONS))

    expect(result.titleKey).toBe('notifications.types.stravaDataDeleted.title')
    expect(result.bodyKey).toBe('notifications.types.stravaDataDeleted.body')
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('names the linked provider and routes to security settings', () => {
    const result = presentNotification(make('idp_linked', { idp_id: 4, idp_name: 'Authentik' }))

    expect(result.icon).toBe(KeyRound)
    expect(result.titleKey).toBe('notifications.types.idpLinked.title')
    expect(result.bodyKey).toBe('notifications.types.idpLinked.body')
    expect(result.bodyParams).toEqual({ name: 'Authentik' })
    expect(result.to).toEqual({ name: 'settings-security' })
  })

  it('falls back to the generic body when the linked provider has no name', () => {
    const result = presentNotification(make('idp_linked', { idp_id: 4, idp_name: null }))

    expect(result.bodyKey).toBe('notifications.types.idpLinked.bodyGeneric')
  })

  it.each([
    ['password_changed', 'passwordChanged'],
    ['password_reset', 'passwordReset'],
    ['password_set_by_admin', 'passwordSetByAdmin'],
    ['mfa_enabled', 'mfaEnabled'],
    ['mfa_disabled', 'mfaDisabled'],
    ['mfa_reset_by_admin', 'mfaResetByAdmin'],
    ['password_change_required_by_admin', 'passwordChangeRequiredByAdmin'],
    ['backup_codes_generated', 'backupCodesGenerated'],
    ['api_key_created', 'apiKeyCreated'],
    ['account_locked', 'accountLocked'],
    ['mfa_locked', 'mfaLocked'],
  ])('presents the %s account-security change', (change, key) => {
    const result = presentNotification(make('account_security_changed', { change }))

    expect(result.icon).toBe(LockKeyhole)
    expect(result.titleKey).toBe(`notifications.types.accountSecurityChanged.${key}.title`)
    expect(result.bodyKey).toBe(`notifications.types.accountSecurityChanged.${key}.body`)
    expect(result.to).toEqual({ name: 'settings-security' })
  })

  it.each(['passwordReset', 'passwordSetByAdmin'])(
    'tells the user that the %s recovery ended their API keys and pending email change',
    (key) => {
      const body = i18n.global.t(`notifications.types.accountSecurityChanged.${key}.body`)

      expect(body).toContain('API keys')
      expect(body).toContain('pending email change')
    },
  )

  it('names the provider of an unlink', () => {
    const result = presentNotification(
      make('account_security_changed', {
        change: 'identity_provider_unlinked',
        idp_id: 4,
        idp_name: 'Authentik',
      }),
    )

    expect(result.titleKey).toBe(
      'notifications.types.accountSecurityChanged.identityProviderUnlinked.title',
    )
    expect(result.bodyKey).toBe(
      'notifications.types.accountSecurityChanged.identityProviderUnlinked.body',
    )
    expect(result.bodyParams).toEqual({ name: 'Authentik' })
  })

  it('falls back to the generic unlink body when the provider has no name', () => {
    const result = presentNotification(
      make('account_security_changed', {
        change: 'identity_provider_unlinked',
        idp_id: 4,
        idp_name: null,
      }),
    )

    expect(result.bodyKey).toBe(
      'notifications.types.accountSecurityChanged.identityProviderUnlinked.bodyGeneric',
    )
  })

  it('degrades to a generic security message for an unknown change', () => {
    const result = presentNotification(
      make('account_security_changed', { change: 'something_new' }),
    )

    expect(result.icon).toBe(LockKeyhole)
    expect(result.titleKey).toBe('notifications.types.accountSecurityChanged.unknown.title')
    expect(result.bodyKey).toBe('notifications.types.accountSecurityChanged.unknown.body')
    expect(result.to).toEqual({ name: 'settings-security' })
  })

  it('presents a sign-in from a new device with its browser and system', () => {
    const result = presentNotification(
      make('new_device_sign_in', {
        browser: 'Firefox',
        operating_system: 'Linux',
        ip_address: '203.0.113.7',
      }),
    )

    expect(result.icon).toBe(LogIn)
    expect(result.titleKey).toBe('notifications.types.newDeviceSignIn.title')
    expect(result.bodyKey).toBe('notifications.types.newDeviceSignIn.body')
    expect(result.bodyParams).toEqual({ browser: 'Firefox', os: 'Linux', ip: '203.0.113.7' })
    expect(result.to).toEqual({ name: 'settings-security' })
  })

  it('routes an admin sign-up approval to the pending user', () => {
    const result = presentNotification(
      make('admin_new_sign_up_approval_request', {
        user_id: 7,
        user_name: 'Ada',
        user_username: 'ada',
      }),
    )

    expect(result.icon).toBe(ShieldAlert)
    expect(result.bodyParams).toEqual({ name: 'Ada', username: 'ada' })
    expect(result.to).toEqual({ name: 'settings-user-detail', params: { id: '7' } })
  })

  it('falls back to a neutral bell for unknown types', () => {
    const result = presentNotification(make('bogus' as NotificationType, NO_OPTIONS))

    expect(result.icon).toBe(Bell)
    expect(result.titleKey).toBe('notifications.types.unknown.title')
    expect(result.to).toBeNull()
  })
})
