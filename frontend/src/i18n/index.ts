import { createI18n } from 'vue-i18n'

import { getStorageItem, setStorageItem } from '@/lib/storage'
import enApp from './locales/en/app.json'
import enNav from './locales/en/nav.json'
import enFooter from './locales/en/footer.json'
import enLogin from './locales/en/login.json'
import enSignup from './locales/en/signup.json'
import enResetPassword from './locales/en/resetPassword.json'
import enVerifyEmail from './locales/en/verifyEmail.json'
import enNotifications from './locales/en/notifications.json'
import enGears from './locales/en/gears.json'
import enActivities from './locales/en/activities.json'
import enSettings from './locales/en/settings.json'
import enHome from './locales/en/home.json'
import enSearch from './locales/en/search.json'
import enUserProfile from './locales/en/userProfile.json'
import enSummary from './locales/en/summary.json'
import enHealth from './locales/en/health.json'
import enUnits from './locales/en/units.json'

/**
 * English message set, assembled from one file per feature namespace. The
 * file name (e.g. `nav.json`) becomes the top-level key (`nav.*`). Add a
 * namespace by dropping a new file in `locales/en/` and importing it here.
 */
const en = {
  app: enApp,
  nav: enNav,
  footer: enFooter,
  login: enLogin,
  signup: enSignup,
  resetPassword: enResetPassword,
  verifyEmail: enVerifyEmail,
  notifications: enNotifications,
  gears: enGears,
  activities: enActivities,
  settings: enSettings,
  home: enHome,
  search: enSearch,
  userProfile: enUserProfile,
  summary: enSummary,
  health: enHealth,
  units: enUnits,
}

/**
 * Shape of a single locale's messages, derived from the English source.
 * `en` is the source of truth; every other locale must match this schema.
 */
export type MessageSchema = typeof en

/**
 * A measurement unit symbol under `units.*` (e.g. `km`, `kg`, `bpm`). Formatters
 * return these keys so they stay free of i18n; the view resolves them through
 * `useUnitFormat`.
 */
export type UnitKey = Exclude<keyof MessageSchema['units'], 'duration'>

/** Locales the app can switch to, in display order. */
export const SUPPORTED_LOCALES = [
  { code: 'en', label: 'English', dir: 'ltr' },
  { code: 'ca', label: 'Català', dir: 'ltr' },
  { code: 'de', label: 'Deutsch', dir: 'ltr' },
  { code: 'es', label: 'Español', dir: 'ltr' },
  { code: 'fr', label: 'Français', dir: 'ltr' },
  { code: 'gl', label: 'Galego', dir: 'ltr' },
  { code: 'it', label: 'Italiano', dir: 'ltr' },
  { code: 'nl', label: 'Nederlands', dir: 'ltr' },
  { code: 'pt-PT', label: 'Português', dir: 'ltr' },
  { code: 'sl', label: 'Slovenščina', dir: 'ltr' },
  { code: 'sv', label: 'Svenska', dir: 'ltr' },
  { code: 'zh-Hans', label: '简体中文', dir: 'ltr' },
  { code: 'zh-Hant', label: '繁體中文', dir: 'ltr' },
  { code: 'pl', label: 'Polski', dir: 'ltr' },
  { code: 'tr', label: 'Türkçe', dir: 'ltr' },
  { code: 'uk', label: 'Українська', dir: 'ltr' },
  { code: 'ro', label: 'Română', dir: 'ltr' },
  { code: 'nb', label: 'Norsk bokmål', dir: 'ltr' },
  { code: 'da', label: 'Dansk', dir: 'ltr' },
  { code: 'fi', label: 'Suomi', dir: 'ltr' },
  { code: 'cs', label: 'Čeština', dir: 'ltr' },
  { code: 'el', label: 'Ελληνικά', dir: 'ltr' },
  { code: 'hu', label: 'Magyar', dir: 'ltr' },
  { code: 'bg', label: 'Български', dir: 'ltr' },
  { code: 'hr', label: 'Hrvatski', dir: 'ltr' },
  { code: 'sr', label: 'Srpski', dir: 'ltr' },
  { code: 'sk', label: 'Slovenčina', dir: 'ltr' },
  { code: 'lt', label: 'Lietuvių', dir: 'ltr' },
  { code: 'lv', label: 'Latviešu', dir: 'ltr' },
  { code: 'et', label: 'Eesti', dir: 'ltr' },
] as const satisfies ReadonlyArray<{ code: string; label: string; dir: 'ltr' | 'rtl' }>

export type LocaleCode = (typeof SUPPORTED_LOCALES)[number]['code']

export const DEFAULT_LOCALE: LocaleCode = 'en'

const STORAGE_KEY = 'locale'

declare module 'vue-i18n' {
  // Make `t()` keys fully type-safe against the English schema.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type
  export interface DefineLocaleMessage extends MessageSchema {}
}

const i18n = createI18n<false>({
  legacy: false,
  locale: DEFAULT_LOCALE,
  // Region/script-aware fallback chain so regional and script variants degrade
  // gracefully (e.g. `pt-BR` → `pt` → `en`, Traditional → Simplified → `en`)
  // instead of jumping straight to English.
  fallbackLocale: {
    'pt-PT': ['pt', DEFAULT_LOCALE],
    'zh-Hant': ['zh-Hans', DEFAULT_LOCALE],
    'zh-Hans': [DEFAULT_LOCALE],
    default: [DEFAULT_LOCALE],
  },
  messages: { en },
})

export default i18n

/**
 * Lazy loaders for non-default locales. Each locale folder holds one file per
 * namespace; the default locale is statically bundled (and excluded here) to
 * avoid a flash of untranslated content on first paint.
 */
const localeFileLoaders = import.meta.glob<{ default: Record<string, unknown> }>([
  './locales/*/*.json',
  '!./locales/en/*.json',
])
const loadedLocales = new Set<LocaleCode>([DEFAULT_LOCALE])

/**
 * Narrows an arbitrary string to a supported locale code.
 *
 * @param value - The candidate locale string.
 * @returns `true` when `value` is a supported locale.
 */
export function isSupportedLocale(value: string): value is LocaleCode {
  return SUPPORTED_LOCALES.some((locale) => locale.code === value)
}

/**
 * Maps a backend preferred-language code to a supported locale. The backend
 * stores canonical BCP 47 tags identical to {@link SUPPORTED_LOCALES}, so each
 * supported code maps to itself and anything else is treated as unknown.
 *
 * @param value - Backend preferred language, e.g. `en` or `pt-PT`.
 * @returns A supported locale, or `null` when no mapping exists.
 */
export function getLocaleForBackendLanguage(value: string | null | undefined): LocaleCode | null {
  if (!value) {
    return null
  }
  return isSupportedLocale(value) ? value : null
}

/**
 * Lazily loads and registers a locale's messages if not already present,
 * merging every namespace file in the locale's folder. Each file's name
 * (without extension) becomes its top-level namespace key.
 *
 * @param locale - The locale to load.
 */
export async function loadLocaleMessages(locale: LocaleCode): Promise<void> {
  if (loadedLocales.has(locale)) {
    return
  }
  const prefix = `./locales/${locale}/`
  const entries = Object.entries(localeFileLoaders).filter(([path]) => path.startsWith(prefix))
  if (entries.length === 0) {
    return
  }
  const messages: Record<string, unknown> = {}
  await Promise.all(
    entries.map(async ([path, loader]) => {
      const namespace = path.slice(prefix.length).replace(/\.json$/, '')
      const loaded = await loader()
      messages[namespace] = loaded.default
    }),
  )
  i18n.global.setLocaleMessage(locale, messages as MessageSchema)
  loadedLocales.add(locale)
}

/**
 * Applies a locale to the active i18n instance, updates the document's
 * `lang`/`dir` attributes, and persists the choice.
 *
 * @param locale - The locale to activate.
 */
export function setI18nLocale(locale: LocaleCode): void {
  const entry = SUPPORTED_LOCALES.find((item) => item.code === locale) ?? SUPPORTED_LOCALES[0]
  i18n.global.locale.value = locale
  document.documentElement.setAttribute('lang', locale)
  document.documentElement.setAttribute('dir', entry.dir)
  setStorageItem(STORAGE_KEY, locale)
}

/**
 * Resolves the initial locale from storage, then browser preference.
 *
 * @returns A supported locale code, falling back to {@link DEFAULT_LOCALE}.
 */
export function getInitialLocale(): LocaleCode {
  const stored = getStorageItem<string>(STORAGE_KEY)
  if (stored && isSupportedLocale(stored)) {
    return stored
  }
  const browser = navigator.language
  if (isSupportedLocale(browser)) {
    return browser
  }
  const base = browser.split('-')[0]
  const match = SUPPORTED_LOCALES.find((locale) => locale.code.split('-')[0] === base)
  return match ? match.code : DEFAULT_LOCALE
}
