import { inject, provide, type InjectionKey, type Ref, ref } from 'vue'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

/**
 * The identity-provider sign-in the server settings page returned from, held above the mail form. The
 * form is rebuilt after every save, so the page holds the sign-in and the form takes it once.
 */
const MAIL_RESUME_KEY: InjectionKey<Ref<IdpStepUpResume | null>> = Symbol('mailStepUpResume')

/**
 * Provides the sign-in the page returned from, if it was for the mail settings.
 *
 * @param resume - The sign-in the page just returned from, if any.
 */
export function provideMailStepUpResume(resume: IdpStepUpResume | null): void {
  provide(MAIL_RESUME_KEY, ref(resume?.action === 'admin_mail_settings_edit' ? resume : null))
}

/**
 * The pending mail-settings sign-in. Clearing `.value` marks it as taken.
 *
 * @returns The pending sign-in, or a ref that holds `null` outside the server settings page.
 */
export function useMailStepUpResume(): Ref<IdpStepUpResume | null> {
  return inject(MAIL_RESUME_KEY, ref(null))
}

/**
 * The identity-provider sign-in the server settings page returned from, held above the settings form for the
 * same reason as {@link MAIL_RESUME_KEY}: the form is rebuilt after every save.
 */
const SETTINGS_RESUME_KEY: InjectionKey<Ref<IdpStepUpResume | null>> =
  Symbol('settingsStepUpResume')

/**
 * Provides the sign-in the page returned from, if it was for the server settings.
 *
 * @param resume - The sign-in the page just returned from, if any.
 */
export function provideSettingsStepUpResume(resume: IdpStepUpResume | null): void {
  provide(SETTINGS_RESUME_KEY, ref(resume?.action === 'admin_server_settings_edit' ? resume : null))
}

/**
 * The pending server-settings sign-in. Clearing `.value` marks it as taken.
 *
 * @returns The pending sign-in, or a ref that holds `null` outside the server settings page.
 */
export function useSettingsStepUpResume(): Ref<IdpStepUpResume | null> {
  return inject(SETTINGS_RESUME_KEY, ref(null))
}
