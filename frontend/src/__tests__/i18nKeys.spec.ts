import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC_DIR = join(process.cwd(), 'src')
const EXCLUDED_FILES = new Set(['types/api.generated.ts'])

// `t`, `$t`, `te`, `tm`, `rt` and `i18n.global.*` calls. The lookbehind rejects identifiers that merely end in
// `t` (`split(`, `emit(`, `get(`), and `.t(` is allowed only through `i18n.global`.
const CALL_PATTERN =
  /(?<![\w$.])(?:\$?(?:t|te|tm|rt)|i18n\.global\.(?:t|te|tm|rt))\(\s*(?:'([^'\n]*)'|"([^"\n]*)"|`([^`\n]*)`)/g
// `<i18n-t keypath="…">` and `keypath: '…'`.
const KEYPATH_PATTERN = /\bkeypath\s*[=:]\s*(?:"([^"\n]*)"|'([^'\n]*)')/g
// Keys held in data and passed to `t(item.labelKey)` later: `labelKey: 'settings.nav.account'`. Restricted to
// values under an English namespace so unrelated `*Key` strings (query keys, storage keys) are ignored.
const KEY_PROPERTY_PATTERN = /\b\w*Key\s*:\s*(?:'([^'\n]*)'|"([^"\n]*)")/g

// The JSON files are read from disk: importing them goes through the vue-i18n plugin, which compiles each leaf
// into an AST object. The file name is the top-level namespace, as in `src/i18n/index.ts`.
const EN_DIR = join(SRC_DIR, 'i18n/locales/en')
const messages: Record<string, unknown> = Object.fromEntries(
  readdirSync(EN_DIR)
    .filter((file) => file.endsWith('.json'))
    .map((file) => [
      file.replace(/\.json$/, ''),
      JSON.parse(readFileSync(join(EN_DIR, file), 'utf8')),
    ]),
)
const namespaces = new Set(Object.keys(messages))

function listSourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) {
      return entry.name === '__tests__' ? [] : listSourceFiles(path)
    }
    const rel = relative(SRC_DIR, path).split('\\').join('/')
    const isSource = /\.(vue|ts)$/.test(entry.name) && !entry.name.endsWith('.spec.ts')
    return isSource && !EXCLUDED_FILES.has(rel) ? [path] : []
  })
}

function resolve(key: string): unknown {
  let node: unknown = messages
  for (const part of key.split('.')) {
    if (typeof node !== 'object' || node === null || !(part in node)) {
      return undefined
    }
    node = (node as Record<string, unknown>)[part]
  }
  return node
}

function isLeafKey(key: string): boolean {
  return typeof resolve(key) === 'string'
}

function isSubtree(prefix: string): boolean {
  if (prefix.endsWith('.')) {
    const node = resolve(prefix.slice(0, -1))
    return typeof node === 'object' && node !== null
  }
  // A partial last segment (`settings.goals.metric_${x}`): some sibling must start with it.
  const dot = prefix.lastIndexOf('.')
  const parent = dot === -1 ? messages : resolve(prefix.slice(0, dot))
  return (
    typeof parent === 'object' &&
    parent !== null &&
    Object.keys(parent).some((name) => name.startsWith(prefix.slice(dot + 1)))
  )
}

interface Usage {
  location: string
  key: string
  dynamic: boolean
}

function collectUsages(): Usage[] {
  const usages: Usage[] = []
  for (const file of listSourceFiles(SRC_DIR)) {
    const text = readFileSync(file, 'utf8')
    const rel = `src/${relative(SRC_DIR, file).split('\\').join('/')}`
    const add = (index: number, raw: string, template: boolean): void => {
      const lines = text.slice(0, index + 1).split('\n')
      if (/^\s*(\*|\/\/|\/\*)/.test(lines[lines.length - 1] ?? '')) {
        return
      }
      const line = lines.length
      if (template && raw.includes('${')) {
        const prefix = raw.slice(0, raw.indexOf('${'))
        if (prefix !== '') {
          usages.push({ location: `${rel}:${line}`, key: prefix, dynamic: true })
        }
        return
      }
      usages.push({ location: `${rel}:${line}`, key: raw, dynamic: false })
    }
    for (const match of text.matchAll(CALL_PATTERN)) {
      const [, single, double, backtick] = match
      add(match.index, single ?? double ?? backtick ?? '', backtick !== undefined)
    }
    for (const match of text.matchAll(KEYPATH_PATTERN)) {
      add(match.index, match[1] ?? match[2] ?? '', false)
    }
    for (const match of text.matchAll(KEY_PROPERTY_PATTERN)) {
      const value = match[1] ?? match[2] ?? ''
      if (namespaces.has(value.split('.')[0] ?? '') && value.includes('.')) {
        add(match.index, value, false)
      }
    }
  }
  return usages
}

describe('i18n keys used in source', () => {
  const usages = collectUsages()

  it('finds translation calls to check', () => {
    expect(usages.length).toBeGreaterThan(500)
  })

  it('resolves every literal key to an English message', () => {
    const missing = usages
      .filter((usage) => !usage.dynamic && !isLeafKey(usage.key))
      .map((usage) => `${usage.location}  ${usage.key}`)
    expect(missing).toEqual([])
  })

  it('resolves every dynamic key prefix to an English subtree', () => {
    const missing = usages
      .filter((usage) => usage.dynamic && !isSubtree(usage.key))
      .map((usage) => `${usage.location}  ${usage.key}\${…}`)
    expect(missing).toEqual([])
  })
})
