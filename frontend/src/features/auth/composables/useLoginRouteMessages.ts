import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

import type { Severity } from '@/types'

import { getQueryString } from '@/composables/useSafeRedirect'

/** An inline alert shown on the login screen. */
export interface AlertState {
  kind: Severity
  message: string
}

/** Maps a boolean status query flag to a translation key and severity. */
const STATUS_FLAG_ALERTS: ReadonlyArray<{ query: string; kind: Severity; key: string }> = [
  { query: 'logoutSuccess', kind: 'success', key: 'login.loggedOut' },
  { query: 'sessionExpired', kind: 'warning', key: 'login.sessionExpired' },
  { query: 'passwordResetSuccess', kind: 'success', key: 'login.passwordResetSuccess' },
  { query: 'passwordResetInvalidLink', kind: 'error', key: 'login.passwordResetInvalidLink' },
  { query: 'onboardingComplete', kind: 'success', key: 'login.onboardingComplete' },
  { query: 'emailVerificationSent', kind: 'info', key: 'login.emailVerificationSent' },
  { query: 'adminApprovalRequired', kind: 'info', key: 'login.adminApprovalRequired' },
  { query: 'verifyEmailInvalidLink', kind: 'error', key: 'login.verifyEmailInvalidLink' },
]

/** Maps an `error` query value from an SSO callback to a translation key. */
const SSO_ERROR_KEYS: Record<string, string> = {
  sso_failed: 'login.ssoFailed',
  sso_cancelled: 'login.ssoCancelled',
  sso_account_not_found: 'login.ssoAccountNotFound',
  sso_account_disabled: 'login.ssoAccountDisabled',
  sso_auto_create_disabled: 'login.ssoAutoCreateDisabled',
  sso_email_missing: 'login.ssoEmailMissing',
}

/**
 * Translates the login screen's status/error query parameters into a single
 * inline alert and the "force local login" flag. Keeping this mapping out of
 * the view makes the (many) redirect states independently testable.
 *
 * @returns Helpers to resolve the initial alert and the force-local-login flag.
 */
export function useLoginRouteMessages() {
  const route = useRoute()
  const { t } = useI18n()

  /**
   * Whether the server redirected the user to fall back to local login.
   *
   * @returns `true` when the `forceLocalLogin` flag is set.
   */
  function shouldForceLocalLogin(): boolean {
    return route.query.forceLocalLogin === 'true'
  }

  /**
   * Resolves the alert to show on first render from status and SSO-error
   * query parameters.
   *
   * @returns The alert to display, or `null` when there is nothing to show.
   */
  function resolveInitialAlert(): AlertState | null {
    if (shouldForceLocalLogin()) {
      return { kind: 'info', message: t('login.forceLocalLogin') }
    }

    const statusMatch = STATUS_FLAG_ALERTS.find((entry) => route.query[entry.query] === 'true')
    if (statusMatch) {
      return { kind: statusMatch.kind, message: t(statusMatch.key) }
    }

    const error = getQueryString(route.query.error)
    if (error) {
      return {
        kind: error === 'sso_cancelled' ? 'info' : 'error',
        message: t(SSO_ERROR_KEYS[error] ?? 'login.ssoErrorUndefined'),
      }
    }

    return null
  }

  return { resolveInitialAlert, shouldForceLocalLogin }
}
