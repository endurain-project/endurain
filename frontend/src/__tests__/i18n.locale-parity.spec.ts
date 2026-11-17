import { readdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { pluralForms } from '@/i18n'

/**
 * Guards against locale drift: every non-English locale folder must carry the
 * same set of namespace files as the English source of truth, so a new feature
 * namespace can't ship translated for some locales and missing for others.
 */
const localesDir = resolve(dirname(fileURLToPath(import.meta.url)), '../i18n/locales')

/**
 * Lists the JSON namespace files in a locale folder, sorted for a stable,
 * order-independent comparison.
 *
 * @param locale - Locale folder name.
 * @returns Sorted namespace file names.
 */
function namespaceFiles(locale: string): string[] {
  return readdirSync(resolve(localesDir, locale))
    .filter((file) => file.endsWith('.json'))
    .sort()
}

const englishFiles = namespaceFiles('en')
const otherLocales = readdirSync(localesDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && entry.name !== 'en')
  .map((entry) => entry.name)
  .sort()

describe('i18n locale parity', () => {
  it('has English namespace files and non-English locales to check', () => {
    expect(englishFiles.length).toBeGreaterThan(0)
    expect(otherLocales.length).toBeGreaterThan(0)
  })

  it.each(otherLocales)('locale "%s" carries every English namespace file', (locale) => {
    expect(namespaceFiles(locale)).toEqual(englishFiles)
  })
})

/**
 * Flattens a locale's namespace files into `namespace.key.path` to string leaves.
 * The JSON is read from disk: importing it goes through the vue-i18n plugin,
 * which compiles each leaf into an AST object.
 *
 * @param locale - Locale folder name.
 * @returns Leaf messages by dotted key.
 */
function flatMessages(locale: string): Map<string, string> {
  const out = new Map<string, string>()
  const walk = (value: unknown, path: string) => {
    if (typeof value === 'string') {
      out.set(path, value)
    } else if (value && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        walk(child, `${path}.${key}`)
      }
    }
  }
  for (const file of namespaceFiles(locale)) {
    const json = JSON.parse(readFileSync(resolve(localesDir, locale, file), 'utf8'))
    walk(json, file.replace(/\.json$/, ''))
  }
  return out
}

describe('i18n plural forms', () => {
  it('gives every plural message the forms its locale uses', () => {
    const pluralKeys = [...flatMessages('en')].filter(([, message]) => message.includes(' | '))
    expect(pluralKeys.length).toBeGreaterThan(0)

    const mismatches: string[] = []
    for (const locale of otherLocales) {
      const expected = pluralForms(locale).length
      const messages = flatMessages(locale)
      for (const [key] of pluralKeys) {
        const message = messages.get(key)
        if (message === undefined) continue
        const actual = message.split(' | ').length
        if (actual !== expected) {
          mismatches.push(`${locale} ${key}: ${actual} forms, expected ${expected}`)
        }
      }
    }
    expect(mismatches).toEqual([])
  })
})
