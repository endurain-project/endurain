import { inject, provide, type InjectionKey, type Ref, ref } from 'vue'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { StepUpAction } from '@/features/security/types'

/**
 * Builds the provide/inject pair that holds the identity-provider sign-in the server settings page returned
 * from, above the form it was for. A form is rebuilt after every save, so the page holds the sign-in and the
 * form takes it once.
 *
 * @param name - The key's description.
 * @param action - The admin operation the sign-in must have been started for.
 * @returns `provide` for the page and `use` for the form.
 */
function createStepUpResume(name: string, action: StepUpAction) {
  const key: InjectionKey<Ref<IdpStepUpResume | null>> = Symbol(name)
  return {
    /**
     * Provides the sign-in the page returned from, if it was for this operation.
     *
     * @param resume - The sign-in the page just returned from, if any.
     */
    provide(resume: IdpStepUpResume | null): void {
      provide(key, ref(resume?.action === action ? resume : null))
    },
    /**
     * The pending sign-in. Clearing `.value` marks it as taken.
     *
     * @returns The pending sign-in, or a ref that holds `null` outside the server settings page.
     */
    use(): Ref<IdpStepUpResume | null> {
      return inject(key, ref(null))
    },
  }
}

const mailResume = createStepUpResume('mailStepUpResume', 'admin_mail_settings_edit')
const settingsResume = createStepUpResume('settingsStepUpResume', 'admin_server_settings_edit')
const logsResume = createStepUpResume('logsStepUpResume', 'admin_server_log_clear')

/** Provides the sign-in the page returned from, if it was for the mail settings. */
export const provideMailStepUpResume = mailResume.provide
/** The pending mail-settings sign-in. */
export const useMailStepUpResume = mailResume.use
/** Provides the sign-in the page returned from, if it was for the server settings. */
export const provideSettingsStepUpResume = settingsResume.provide
/** The pending server-settings sign-in. */
export const useSettingsStepUpResume = settingsResume.use
/** Provides the sign-in the page returned from, if it was for clearing the server log. */
export const provideLogsStepUpResume = logsResume.provide
/** The pending log-clear sign-in. */
export const useLogsStepUpResume = logsResume.use
