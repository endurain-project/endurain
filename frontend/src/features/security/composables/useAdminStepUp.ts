import { computed, watch } from 'vue'

import type { StepUpAction } from '@/features/security/types'
import type { IdpStepUpResume, StepUpPending } from '@/features/security/composables/useIdpStepUp'

import { useProfileQuery } from '@/features/profile/composables/useProfile'

/**
 * What the step-up dialog of an admin operation asks for: the signed-in administrator's own
 * credentials, never the target user's. An administrator without a local password signs in again with
 * their identity provider instead.
 *
 * @returns Whether the dialog needs a password and whether it needs an MFA code.
 */
export function useAdminStepUp() {
  const profileQuery = useProfileQuery()

  return {
    requirePassword: computed(() => profileQuery.data.value?.hasLocalPassword ?? true),
    requireMfa: computed(() => profileQuery.data.value?.mfaEnabled ?? false),
  }
}

/**
 * Runs `onResume` once, when the identity-provider sign-in the page returned from was started for this
 * admin operation and this dialog. Re-evaluated as what `matches` reads changes, since the page may still
 * be loading the target.
 *
 * @param resume - Getter for the sign-in the page just returned from, if any.
 * @param action - The admin operation the dialog performs.
 * @param matches - Whether the stored context belongs to this dialog and its current target.
 * @param onResume - Reopens the dialog with the sign-in proof.
 */
export function useResumeOnce(
  resume: () => IdpStepUpResume | null,
  action: StepUpAction,
  matches: (pending: StepUpPending) => boolean,
  onResume: (resume: IdpStepUpResume) => void,
): void {
  let consumed = false
  watch(
    () => {
      const returned = resume()
      return returned?.action === action && matches(returned.pending) ? returned : null
    },
    (returned) => {
      if (!consumed && returned) {
        consumed = true
        onResume(returned)
      }
    },
    { immediate: true },
  )
}

/**
 * The target id (`userId` or `idpId`) an identity-provider return was started for, for any of the
 * admin operations a page hosts.
 *
 * @param resume - The identity-provider sign-in the page just returned from, if any.
 * @param actions - The admin operations the page hosts.
 * @param key - The context entry that holds the id.
 * @returns The id, or `null` when the return belongs to another page's operation.
 */
export function resumeTargetId(
  resume: IdpStepUpResume | null,
  actions: readonly StepUpAction[],
  key: 'userId' | 'idpId',
): number | null {
  const id = resume?.pending[key]
  return resume && actions.includes(resume.action) && typeof id === 'number' ? id : null
}
