import { afterEach, describe, expect, it } from 'vitest'

import i18n, { DEFAULT_LOCALE, SUPPORTED_LOCALES, pluralForms, type LocaleCode } from '@/i18n'

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

describe('plural rule', () => {
  const key = 'test.plural'
  const original = i18n.global.getLocaleMessage('en')

  /** Sets a one-key message for a locale and selects that locale. */
  function use(code: LocaleCode, message: string): (count: number) => string {
    i18n.global.mergeLocaleMessage(code, { test: { plural: message } })
    locale.value = code
    return (count) => t(key, { count })
  }

  afterEach(() => {
    for (const { code } of SUPPORTED_LOCALES) {
      const messages = i18n.global.getLocaleMessage(code) as Record<string, unknown>
      delete messages.test
      i18n.global.setLocaleMessage(code, messages as typeof original)
    }
  })

  it.each([
    ['pl', ['one', 'few', 'many']],
    ['sl', ['one', 'two', 'few', 'other']],
    ['lv', ['zero', 'one', 'other']],
    ['fr', ['one', 'other']],
    ['zh-Hans', ['other']],
    ['en', ['one', 'other']],
  ] as const)('lists the forms of %s', (code, forms) => {
    expect(pluralForms(code)).toEqual(forms)
  })

  it('picks one, few and many in Polish', () => {
    const text = use('pl', 'one | few | many')
    expect([1, 2, 5, 22, 25].map(text)).toEqual(['one', 'few', 'many', 'few', 'many'])
  })

  it('picks one, two, few and other in Slovenian', () => {
    const text = use('sl', 'one | two | few | other')
    expect([1, 2, 3, 5, 101, 102].map(text)).toEqual(['one', 'two', 'few', 'other', 'one', 'two'])
  })

  it('picks zero, one and other in Latvian', () => {
    const text = use('lv', 'zero | one | other')
    expect([0, 1, 2, 10, 21].map(text)).toEqual(['zero', 'one', 'other', 'zero', 'one'])
  })

  it('treats 0 and 1 as one in French', () => {
    const text = use('fr', 'one | other')
    expect([0, 1].map(text)).toEqual(['one', 'one'])
    expect([2, 1_000_000].map(text)).toEqual(['other', 'other'])
  })

  it('uses the single form in Chinese for any count', () => {
    const text = use('zh-Hans', '{count} items')
    expect([0, 1, 5].map(text)).toEqual(['0 items', '1 items', '5 items'])
  })

  it('falls back to the last form when a message has fewer forms than the locale', () => {
    const text = use('pl', 'one | few')
    expect([1, 2, 5].map(text)).toEqual(['one', 'few', 'few'])
  })
})
