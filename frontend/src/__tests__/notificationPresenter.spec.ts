import { describe, expect, it } from 'vitest'
import {
  Activity,
  Bell,
  CopyCheck,
  KeyRound,
  ShieldAlert,
  UserCheck,
  UserPlus,
  Unplug,
  Watch,
} from '@lucide/vue'

import type { Notification } from '@/features/notifications/types'

import { presentNotification } from '@/features/notifications/utils/notificationPresenter'

/**
 * Builds a notification with sensible defaults so each test only states the
 * fields it cares about.
 *
 * @param type - Numeric notification type, or `null`.
 * @param options - The per-type metadata bag.
 * @returns A notification model for the presenter.
 */
function make(type: number | null, options: Record<string, unknown> | null = null): Notification {
  return { id: 1, type, read: false, options, createdAt: null, userId: 5 }
}

describe('presentNotification', () => {
  it('presents a new-activity notification with a deep link', () => {
    const result = presentNotification(make(1, { activity_id: 42 }))

    expect(result.icon).toBe(Activity)
    expect(result.titleKey).toBe('notifications.types.newActivity.title')
    expect(result.bodyKey).toBe('notifications.types.newActivity.body')
    expect(result.to).toEqual({ name: 'activity', params: { id: '42' } })
  })

  it('drops the activity link when the id is missing', () => {
    expect(presentNotification(make(1, {})).to).toBeNull()
  })

  it('presents a duplicate-activity notification', () => {
    const result = presentNotification(make(2, { activity_id: 7 }))

    expect(result.icon).toBe(CopyCheck)
    expect(result.titleKey).toBe('notifications.types.duplicateActivity.title')
    expect(result.to).toEqual({ name: 'activity', params: { id: '7' } })
  })

  it('links a follower request to the viewer followers list', () => {
    const result = presentNotification(make(11, { user_name: 'Ada', user_username: 'ada' }), {
      currentUserId: 9,
    })

    expect(result.icon).toBe(UserPlus)
    expect(result.bodyParams).toEqual({ name: 'Ada', username: 'ada' })
    expect(result.to).toEqual({ name: 'user', params: { id: '9' }, query: { tab: 'followers' } })
  })

  it('omits the follower-request link without a current user id', () => {
    expect(presentNotification(make(11, {})).to).toBeNull()
  })

  it('coerces missing follower fields to empty strings', () => {
    const result = presentNotification(make(11, {}), { currentUserId: 1 })

    expect(result.bodyParams).toEqual({ name: '', username: '' })
  })

  it('links an accepted follower request to that user', () => {
    const result = presentNotification(
      make(12, { user_id: 3, user_name: 'Ada', user_username: 'ada' }),
    )

    expect(result.icon).toBe(UserCheck)
    expect(result.to).toEqual({ name: 'user', params: { id: '3' } })
  })

  it('routes a Garmin token expiry to settings integrations', () => {
    const result = presentNotification(make(21))

    expect(result.icon).toBe(Watch)
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('routes a Strava token expiry to settings integrations', () => {
    const result = presentNotification(make(22))

    expect(result.icon).toBe(Unplug)
    expect(result.titleKey).toBe('notifications.types.stravaTokenExpired.title')
    expect(result.to).toEqual({ name: 'settings', query: { tab: 'integrations' } })
  })

  it('names the linked provider and routes to security settings', () => {
    const result = presentNotification(make(31, { idp_id: 4, idp_name: 'Authentik' }))

    expect(result.icon).toBe(KeyRound)
    expect(result.titleKey).toBe('notifications.types.idpLinked.title')
    expect(result.bodyKey).toBe('notifications.types.idpLinked.body')
    expect(result.bodyParams).toEqual({ name: 'Authentik' })
    expect(result.to).toEqual({ name: 'settings-security' })
  })

  it('falls back to the generic body when the linked provider has no name', () => {
    const result = presentNotification(make(31, { idp_id: 4, idp_name: null }))

    expect(result.bodyKey).toBe('notifications.types.idpLinked.bodyGeneric')
  })

  it('routes an admin sign-up approval to the pending user', () => {
    const result = presentNotification(
      make(101, { user_id: 7, user_name: 'Ada', user_username: 'ada' }),
    )

    expect(result.icon).toBe(ShieldAlert)
    expect(result.bodyParams).toEqual({ name: 'Ada', username: 'ada' })
    expect(result.to).toEqual({ name: 'settings-user-detail', params: { id: '7' } })
  })

  it('routes an admin sign-up approval without a user id to the users list', () => {
    const result = presentNotification(make(101, { user_name: 'Ada', user_username: 'ada' }))

    expect(result.to).toEqual({ name: 'settings-users' })
  })

  it('falls back to a neutral bell for unknown types', () => {
    const result = presentNotification(make(999))

    expect(result.icon).toBe(Bell)
    expect(result.titleKey).toBe('notifications.types.unknown.title')
    expect(result.to).toBeNull()
  })

  it('handles a null type', () => {
    expect(presentNotification(make(null)).icon).toBe(Bell)
  })
})
