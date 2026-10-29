import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'

import type { IdpReauth, StepUpAction } from '@/features/security/types'

import { generateCodeChallenge, generateCodeVerifier } from '@/features/auth/utils/pkce'
import { HttpError } from '@/services/http'
import { queryKeys } from '@/services/queryKeys'
import { useToasts } from '@/composables/useToasts'
import { startIdpStepUp } from '@/features/security/services/idpStepUp'

const STORAGE_KEY = 'idp_step_up'
const STORED_TTL_MS = 10 * 60 * 1000
const TICKET_PARAM = 'step_up_ticket'
const ERROR_PARAM = 'step_up_error'
const IDP_REAUTH_REQUIRED_PROBLEM = 'urn:endurain:error:idp-reauth-required'

/** What the UI needs to reopen the right dialog after the provider round-trip. Never a secret. */
export type StepUpPending = Record<string, unknown>

/** Why a returning step-up did not yield a ticket. */
export type IdpStepUpFailure = 'failed' | 'not_fresh'

/**
 * A successful return from the identity provider.
 *
 * @property action - The operation the ticket was started for.
 * @property reauth - The ticket and PKCE verifier to send with the sensitive request.
 * @property pending - The context stored when the step-up started.
 * @property error - Always absent; lets callers tell a resume from a failure.
 */
export interface IdpStepUpResume {
  error?: undefined
  action: StepUpAction
  reauth: IdpReauth
  pending: StepUpPending
}

/** The outcome of returning from the identity provider: a resume or a failure. */
export type IdpStepUpReturn = IdpStepUpResume | { error: IdpStepUpFailure }

interface StoredStepUp {
  action: StepUpAction
  verifier: string
  idpId: number
  pending: StepUpPending
  createdAt: number
}

/**
 * Whether an error is the backend asking for an identity-provider sign-in.
 *
 * @param error - The error a sensitive request failed with.
 * @returns `true` for the `idp-reauth-required` problem type.
 */
export function isIdpReauthRequired(error: unknown): boolean {
  return error instanceof HttpError && error.type === IDP_REAUTH_REQUIRED_PROBLEM
}

/** Reads and removes the stored entry; `null` when absent, malformed or older than the TTL. */
function takeStoredStepUp(now: number): StoredStepUp | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    sessionStorage.removeItem(STORAGE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as Partial<StoredStepUp>
    if (
      typeof parsed.action !== 'string' ||
      typeof parsed.verifier !== 'string' ||
      parsed.verifier.length === 0 ||
      typeof parsed.createdAt !== 'number' ||
      now - parsed.createdAt > STORED_TTL_MS
    ) {
      return null
    }
    return {
      action: parsed.action,
      verifier: parsed.verifier,
      idpId: typeof parsed.idpId === 'number' ? parsed.idpId : 0,
      pending: parsed.pending ?? {},
      createdAt: parsed.createdAt,
    }
  } catch {
    return null
  }
}

/**
 * Consumes the step-up outcome the identity-provider callback left in the URL
 * fragment. The fragment is stripped at once (path and query are kept) and the
 * stored entry is removed after it is read.
 *
 * @param now - Current timestamp, for the entry's expiry.
 * @returns The outcome, or `null` when the URL carries no step-up result.
 */
export function consumeIdpStepUpReturn(now = Date.now()): IdpStepUpReturn | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const ticket = params.get(TICKET_PARAM)
  const error = params.get(ERROR_PARAM)
  if (!ticket && !error) {
    return null
  }
  history.replaceState(history.state, '', window.location.pathname + window.location.search)

  const stored = takeStoredStepUp(now)
  if (error || !ticket || !stored) {
    return { error: error === 'not_fresh' ? 'not_fresh' : 'failed' }
  }
  return {
    action: stored.action,
    reauth: { ticket, codeVerifier: stored.verifier },
    pending: stored.pending,
  }
}

/**
 * Handles the backend's `idp-reauth-required` challenge. The account has no
 * local password, so the profile is refetched and the step-up dialogs switch to
 * their identity-provider mode.
 *
 * @returns A handler that returns `true` when it consumed the error.
 */
export function useIdpReauthChallenge() {
  const { t } = useI18n()
  const toasts = useToasts()
  const client = useQueryClient()

  return (error: unknown): boolean => {
    if (!isIdpReauthRequired(error)) {
      return false
    }
    toasts.error(t('settings.security.stepUp.reauthRequired'))
    void client.invalidateQueries({ queryKey: queryKeys.profile.all() })
    return true
  }
}

/**
 * Starts identity-provider step-up for accounts without a local password.
 *
 * @returns `start`, which stores the PKCE verifier and navigates to the provider.
 */
export function useIdpStepUp() {
  const route = useRoute()

  /**
   * Generates the PKCE pair, remembers the verifier and the dialog context, and
   * sends the browser to the provider to sign in again.
   *
   * @param idpId - The linked identity-provider id.
   * @param action - The sensitive operation being authorised.
   * @param pending - What the UI needs to reopen the right dialog on return; no secrets.
   * @throws {HttpError} When the start request fails.
   */
  async function start(idpId: number, action: StepUpAction, pending: StepUpPending): Promise<void> {
    const verifier = generateCodeVerifier()
    const challenge = await generateCodeChallenge(verifier)
    const url = await startIdpStepUp(idpId, action, challenge, route.path)
    const entry: StoredStepUp = { action, verifier, idpId, pending, createdAt: Date.now() }
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entry))
    window.location.assign(url)
  }

  return { start }
}
