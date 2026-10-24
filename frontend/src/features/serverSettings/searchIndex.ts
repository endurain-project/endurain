import type { SettingsTab } from '@/features/serverSettings/settingsTabs'

/**
 * One searchable setting or section. `id` is the `data-setting` attribute of the
 * element the search jumps to.
 *
 * @property id - The `data-setting` value of the target element.
 * @property tab - The tab the target lives on.
 * @property labelKey - i18n key of the setting's label (or the section title).
 * @property sectionId - `id` of the card the setting sits in; absent on a section entry.
 * @property envVars - Environment variables that set it, so they can be searched by name.
 */
export interface SettingsSearchEntry {
  id: string
  tab: SettingsTab
  labelKey: string
  sectionId?: string
  envVars?: readonly string[]
}

/** A matched entry with its display strings resolved. */
export interface SettingsSearchResult {
  entry: SettingsSearchEntry
  label: string
  /** The card title the setting sits in, or null for a section entry. */
  section: string | null
  tabLabel: string
}

/** Section cards: the title key of each, shared by the section entry and its fields. */
const SECTIONS = {
  general: { id: 'section-general', tab: 'general', labelKey: 'settings.server.general.title' },
  retention: {
    id: 'section-retention',
    tab: 'general',
    labelKey: 'settings.server.retention.title',
  },
  photo: { id: 'section-photo', tab: 'general', labelKey: 'settings.server.photo.title' },
  sso: { id: 'section-sso', tab: 'access', labelKey: 'settings.server.sso.title' },
  signup: { id: 'section-signup', tab: 'access', labelKey: 'settings.server.signup.title' },
  password: { id: 'section-password', tab: 'access', labelKey: 'settings.server.password.title' },
  session: { id: 'section-session', tab: 'access', labelKey: 'settings.server.session.title' },
  sharing: { id: 'section-sharing', tab: 'access', labelKey: 'settings.server.sharing.title' },
  maps: { id: 'section-maps', tab: 'maps', labelKey: 'settings.server.maps.title' },
  geocoding: {
    id: 'section-geocoding',
    tab: 'maps',
    labelKey: 'settings.server.geocoding.title',
  },
  email: { id: 'section-email', tab: 'email', labelKey: 'settings.server.email.title' },
} as const satisfies Record<string, SettingsSearchEntry>

type SectionName = keyof typeof SECTIONS

/**
 * Builds a field entry inside a section.
 *
 * @param section - The card the field sits in.
 * @param id - The field's `data-setting` value.
 * @param labelKey - i18n key of the field's label.
 * @param envVars - Environment variables that set the field.
 * @returns The search entry.
 */
function field(
  section: SectionName,
  id: string,
  labelKey: string,
  envVars?: readonly string[],
): SettingsSearchEntry {
  const { id: sectionId, tab } = SECTIONS[section]
  return { id, tab, labelKey, sectionId, envVars }
}

/** Every searchable section and field, in page order. */
export const SETTINGS_SEARCH_ENTRIES: readonly SettingsSearchEntry[] = [
  SECTIONS.general,
  field('general', 'general-units', 'settings.server.general.units'),
  field('general', 'general-currency', 'settings.server.general.currency'),
  field('general', 'general-num-records', 'settings.server.general.numRecords'),
  SECTIONS.retention,
  field(
    'retention',
    'retention-read-notifications',
    'settings.server.retention.readNotifications',
    ['READ_NOTIFICATION_RETENTION_DAYS'],
  ),
  SECTIONS.photo,

  SECTIONS.sso,
  field('sso', 'sso-enabled', 'settings.server.sso.enabled'),
  field('sso', 'sso-local-login', 'settings.server.sso.localLogin'),
  field('sso', 'sso-auto-redirect', 'settings.server.sso.autoRedirect'),
  SECTIONS.signup,
  field('signup', 'signup-enabled', 'settings.server.signup.enabled'),
  field('signup', 'signup-admin-approval', 'settings.server.signup.adminApproval'),
  field('signup', 'signup-email-verification', 'settings.server.signup.emailVerification'),
  SECTIONS.password,
  field('password', 'password-type', 'settings.server.password.type'),
  field('password', 'password-length-regular', 'settings.server.password.lengthRegular'),
  field('password', 'password-length-admin', 'settings.server.password.lengthAdmin'),
  SECTIONS.session,
  field('session', 'session-timeouts-enabled', 'settings.server.session.timeoutsEnabled', [
    'SESSION_IDLE_TIMEOUT_ENABLED',
  ]),
  field('session', 'session-idle-hours', 'settings.server.session.idleHours', [
    'SESSION_IDLE_TIMEOUT_HOURS',
  ]),
  field('session', 'session-absolute-hours', 'settings.server.session.absoluteHours', [
    'SESSION_ABSOLUTE_TIMEOUT_HOURS',
  ]),
  field('session', 'session-access-minutes', 'settings.server.session.accessMinutes', [
    'ACCESS_TOKEN_EXPIRE_MINUTES',
  ]),
  field('session', 'session-refresh-days', 'settings.server.session.refreshDays', [
    'REFRESH_TOKEN_EXPIRE_DAYS',
  ]),
  SECTIONS.sharing,
  field('sharing', 'sharing-enabled', 'settings.server.sharing.enabled'),
  field('sharing', 'sharing-user-info', 'settings.server.sharing.userInfo'),

  SECTIONS.maps,
  field('maps', 'maps-template', 'settings.server.maps.template'),
  field('maps', 'maps-url', 'settings.server.maps.url'),
  field('maps', 'maps-attribution', 'settings.server.maps.attribution'),
  field('maps', 'maps-api-key', 'settings.server.maps.apiKey'),
  field('maps', 'maps-background-color', 'settings.server.maps.backgroundColor'),
  field('maps', 'maps-regenerate-thumbnails', 'settings.server.maps.regenerateThumbnails'),
  SECTIONS.geocoding,
  field('geocoding', 'geocoding-service', 'settings.server.geocoding.service', [
    'REVERSE_GEO_PROVIDER',
  ]),
  field('geocoding', 'geocoding-host', 'settings.server.geocoding.host', [
    'NOMINATIM_API_HOST',
    'PHOTON_API_HOST',
  ]),
  field('geocoding', 'geocoding-use-https', 'settings.server.geocoding.useHttps', [
    'NOMINATIM_API_USE_HTTPS',
    'PHOTON_API_USE_HTTPS',
  ]),
  field('geocoding', 'geocoding-rate-limit', 'settings.server.geocoding.rateLimit', [
    'REVERSE_GEO_RATE_LIMIT',
  ]),
  field('geocoding', 'geocoding-api-key', 'settings.server.geocoding.apiKey', [
    'GEOCODES_MAPS_API',
  ]),

  SECTIONS.email,
  field('email', 'email-host', 'settings.server.email.host', ['SMTP_HOST']),
  field('email', 'email-port', 'settings.server.email.port', ['SMTP_PORT']),
  field('email', 'email-security', 'settings.server.email.security', ['SMTP_SECURE']),
  field('email', 'email-username', 'settings.server.email.username', ['SMTP_USERNAME']),
  field('email', 'email-password', 'settings.server.email.password', ['SMTP_PASSWORD']),
  field('email', 'email-from-address', 'settings.server.email.fromAddress', ['SMTP_FROM']),
]

/** Maximum number of results offered at once. */
const MAX_RESULTS = 8

/**
 * Lowercases and strips accents so matching ignores case and diacritics.
 *
 * @param text - The text to normalize.
 * @returns The normalized text.
 */
function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

/**
 * Finds the settings matching a query. Every whitespace-separated word must
 * appear in the setting's label, section title, tab name or environment variable
 * names; labels that start with the query rank first, then labels containing every
 * word, then the rest, each in page order.
 *
 * @param query - What the user typed.
 * @param translate - Resolves an i18n key to its text.
 * @param tabLabel - Resolves a tab to its display name.
 * @returns The matches, best first, capped at a handful.
 */
export function searchSettings(
  query: string,
  translate: (key: string) => string,
  tabLabel: (tab: SettingsTab) => string,
): SettingsSearchResult[] {
  const normalizedQuery = normalize(query).trim()
  if (!normalizedQuery) {
    return []
  }
  const words = normalizedQuery.split(/\s+/)
  const sectionTitles = new Map<string, string>(
    Object.values(SECTIONS).map((section) => [section.id, translate(section.labelKey)]),
  )

  const ranked: { result: SettingsSearchResult; rank: number }[] = []
  for (const entry of SETTINGS_SEARCH_ENTRIES) {
    const label = translate(entry.labelKey)
    const section = entry.sectionId ? (sectionTitles.get(entry.sectionId) ?? null) : null
    const tab = tabLabel(entry.tab)
    const normalizedLabel = normalize(label)
    const haystack = normalize([label, section, tab, ...(entry.envVars ?? [])].join(' '))
    if (!words.every((word) => haystack.includes(word))) {
      continue
    }
    let rank = 2
    if (normalizedLabel.startsWith(normalizedQuery)) {
      rank = 0
    } else if (words.every((word) => normalizedLabel.includes(word))) {
      rank = 1
    }
    ranked.push({ result: { entry, label, section, tabLabel: tab }, rank })
  }
  // Array#sort is stable, so equal ranks keep page order.
  return ranked
    .sort((a, b) => a.rank - b.rank)
    .slice(0, MAX_RESULTS)
    .map(({ result }) => result)
}
