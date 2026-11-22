import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { SETTINGS_SEARCH_ENTRIES, searchSettings } from '@/features/serverSettings/searchIndex'
import { parseSettingsTab } from '@/features/serverSettings/settingsTabs'

// Read the raw file: the i18n build plugin turns imported messages into compiled objects.
const en = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/i18n/locales/en/settings.json'), 'utf-8'),
) as { server: { tabs: Record<string, string> } }

/** Resolves a dotted `settings.server.*` key against the English catalog. */
function translate(key: string): string {
  const resolved = key
    .replace(/^settings\./, '')
    .split('.')
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], en)
  return String(resolved)
}

/** English tab names, as the page shows them. */
function tabLabel(tab: string): string {
  return en.server.tabs[tab] ?? ''
}

describe('searchSettings', () => {
  it('returns nothing for a blank query', () => {
    expect(searchSettings('   ', translate, tabLabel)).toEqual([])
  })

  it('finds a setting by its label, ignoring case', () => {
    const results = searchSettings('IDLE TIMEOUT', translate, tabLabel)
    expect(results[0]?.entry.id).toBe('session-idle-hours')
  })

  it('finds a setting by the environment variable that sets it', () => {
    const results = searchSettings('SMTP_HOST', translate, tabLabel)
    expect(results.map((result) => result.entry.id)).toEqual(['email-host'])
  })

  it('requires every word to match', () => {
    expect(searchSettings('idle banana', translate, tabLabel)).toEqual([])
  })

  it('ignores accents in both query and text', () => {
    const results = searchSettings(
      'Señal',
      (key) => (key.endsWith('units') ? 'Señal' : 'x'),
      () => '',
    )
    expect(results.map((result) => result.entry.id)).toContain('general-units')
  })

  it('ranks a label that starts with the query before one that merely contains it', () => {
    const results = searchSettings('host', translate, tabLabel)
    expect(results.length).toBeGreaterThan(1)
    expect(results[0]?.label.toLowerCase().startsWith('host')).toBe(true)
  })

  it('names the section and tab of a field result', () => {
    const [result] = searchSettings('refresh token', translate, tabLabel)
    expect(result?.section).toBe('Sessions')
    expect(result?.tabLabel).toBe('Access & security')
  })

  it('gives a section result no parent section', () => {
    const result = searchSettings('Sessions', translate, tabLabel).find(
      (entry) => entry.entry.id === 'section-session',
    )
    expect(result?.section).toBeNull()
  })
})

describe('search index', () => {
  it('has unique ids', () => {
    const ids = SETTINGS_SEARCH_ENTRIES.map((entry) => entry.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('points every field at a section on the same tab', () => {
    const sections = new Map(
      SETTINGS_SEARCH_ENTRIES.filter((entry) => !entry.sectionId).map((entry) => [entry.id, entry]),
    )
    for (const entry of SETTINGS_SEARCH_ENTRIES.filter((candidate) => candidate.sectionId)) {
      expect(sections.get(entry.sectionId ?? '')?.tab).toBe(entry.tab)
    }
  })

  it('resolves every label in the English catalog', () => {
    for (const entry of SETTINGS_SEARCH_ENTRIES) {
      expect(translate(entry.labelKey)).not.toBe('undefined')
    }
  })
})

describe('parseSettingsTab', () => {
  it('accepts a known tab', () => {
    expect(parseSettingsTab('maps')).toBe('maps')
  })

  it('falls back to General for anything else', () => {
    expect(parseSettingsTab('nope')).toBe('general')
    expect(parseSettingsTab(undefined)).toBe('general')
    expect(parseSettingsTab(['maps'])).toBe('general')
  })
})
