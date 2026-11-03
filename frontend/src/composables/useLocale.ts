import { storeToRefs } from 'pinia'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { SUPPORTED_LOCALES, loadLocaleMessages, setI18nLocale, type LocaleCode } from '@/i18n'
import { useToasts } from '@/composables/useToasts'
import { useAuthStore } from '@/features/auth/stores/auth'
import { useAppConfig } from '@/features/config/composables/useAppConfig'
import { useSavePreferredLanguage } from '@/features/profile/composables/useProfile'
import { isStaleWrite } from '@/services/ifMatch'

/**
 * Locale controller exposing the active locale, the translator, and a
 * lazy-loading setter that persists the user's choice. The exposed locale
 * list honours the instance's `enabledLocales` runtime config, so a hosted
 * deployment can restrict which languages it offers from one bundle.
 *
 * @returns The reactive `locale`, the `t` translator, the `availableLocales`
 *   list, and an async `setLocale` action.
 */
export function useLocale() {
  const { t, locale } = useI18n()
  const { config } = useAppConfig()
  const { isAuthenticated } = storeToRefs(useAuthStore())
  const savePreferredLanguage = useSavePreferredLanguage()
  const toasts = useToasts()

  const availableLocales = computed(() => {
    const enabled = config.value.enabledLocales
    const allowed =
      !enabled || enabled.length === 0
        ? SUPPORTED_LOCALES
        : SUPPORTED_LOCALES.filter((entry) => new Set<LocaleCode>(enabled).has(entry.code))
    // Never hide every option: fall back to all locales on a misconfiguration.
    const locales = allowed.length > 0 ? allowed : SUPPORTED_LOCALES
    // Display locales alphabetically by their native label.
    return [...locales].sort((a, b) => a.label.localeCompare(b.label))
  })

  /**
   * Switches the active locale, lazy-loading its messages first. When signed in
   * the choice is also saved to the profile, which is the source of truth the
   * session restore reads the language from; a failed save is reported but the
   * switch stands for this session.
   *
   * @param next - The locale to activate.
   */
  async function setLocale(next: LocaleCode): Promise<void> {
    await loadLocaleMessages(next)
    setI18nLocale(next)
    if (!isAuthenticated.value) {
      return
    }
    try {
      await savePreferredLanguage(next)
    } catch (error) {
      toasts.error(isStaleWrite(error) ? t('app.staleError') : t('app.error.toast'))
    }
  }

  return { t, locale, availableLocales, setLocale }
}
