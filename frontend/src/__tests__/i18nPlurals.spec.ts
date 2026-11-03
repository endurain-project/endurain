import { afterEach, describe, expect, it } from 'vitest'

import i18n, { DEFAULT_LOCALE, loadLocaleMessages } from '@/i18n'

const { t, locale } = i18n.global

afterEach(() => {
  locale.value = DEFAULT_LOCALE
})

describe('English plural forms', () => {
  it.each([
    ['notifications.badge', 1, '1 unread notification'],
    ['notifications.badge', 3, '3 unread notifications'],
    ['activities.list.resultCount', 1, '1 activity'],
    ['activities.list.resultCount', 12, '12 activities'],
    ['settings.goals.count', 1, 'There is a total of 1 goal:'],
    ['settings.goals.count', 4, 'There is a total of 4 goals:'],
  ] as const)('%s with %i', (key, count, expected) => {
    expect(t(key, { count })).toBe(expected)
  })

  it('uses the plural form for zero', () => {
    expect(t('notifications.badge', { count: 0 })).toBe('0 unread notifications')
  })

  it('pluralizes backup codes on the total', () => {
    const text = (unused: number, total: number) =>
      t('settings.security.mfa.backupRemaining', { unused, total, count: total })
    expect(text(1, 1)).toBe('1 of 1 backup code remaining.')
    expect(text(3, 10)).toBe('3 of 10 backup codes remaining.')
  })
})

describe('locales that still have a single-form string', () => {
  it('renders the count without leaking a plural separator', async () => {
    await loadLocaleMessages('pt-PT')
    locale.value = 'pt-PT'

    for (const count of [0, 1, 5]) {
      const text = t('notifications.badge', { count })
      expect(text).toContain(String(count))
      expect(text).not.toContain('|')
    }
  })
})
