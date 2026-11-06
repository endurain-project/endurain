import { computed, watch } from 'vue'

import type { StepUpAction } from '@/features/security/types'
import type { IdpStepUpResume, StepUpPending } from '@/features/security/composables/useIdpStepUp'

import { useProfileQuery } from '@/features/profile/composables/useProfile'
import { useMfaStatusQuery } from '@/features/security/composables/useSecurity'

/**
 * What the step-up dialog of an admin operation asks for: the signed-in administrator's own
 * credentials, never the target user's. An administrator without a local password signs in again with
 * their identity provider instead.
 *
 * @returns Whether the dialog needs a password and whether it needs an MFA code.
 */
export function useAdminStepUp() {
  const profileQuery = useProfileQuery()
  const mfaStatusQuery = useMfaStatusQuery()

  return {
    requirePassword: computed(() => profileQuery.data.value?.hasLocalPassword ?? true),
    requireMfa: computed(() => mfaStatusQuery.data.value?.enabled ?? false),
  }
}

/**
 * Runs `onResume` once, when the identity-provider sign-in the page returned from was started for this
 * admin operation on this user. Re-evaluated as the user arrives, since the page may still be loading it.
 *
 * @param resume - Getter for the sign-in the page just returned from, if any.
 * @param action - The admin operation the dialog performs.
 * @param userId - Getter for the user the dialog acts on.
 * @param onResume - Reopens the dialog with the sign-in proof.
 * @param accepts - Narrows a match further by the stored context (for operations sharing an action).
 */
export function useResumeOnce(
  resume: () => IdpStepUpResume | null,
  action: StepUpAction,
  userId: () => number | null,
  onResume: (resume: IdpStepUpResume) => void,
  accepts: (pending: StepUpPending) => boolean = () => true,
): void {
  let consumed = false
  watch(
    userId,
    (id) => {
      const returned = resume()
      if (
        !consumed &&
        returned?.action === action &&
        id !== null &&
        returned.pending.userId === id &&
        accepts(returned.pending)
      ) {
        consumed = true
        onResume(returned)
      }
    },
    { immediate: true },
  )
}

/**
 * The target user an identity-provider return was started for, for any of the admin operations.
 *
 * @param resume - The identity-provider sign-in the page just returned from, if any.
 * @param actions - The admin operations the page hosts.
 * @returns The user id, or `null` when the return belongs to another page's operation.
 */
export function resumeUserId(
  resume: IdpStepUpResume | null,
  actions: readonly StepUpAction[],
): number | null {
  const userId = resume?.pending.userId
  return resume && actions.includes(resume.action) && typeof userId === 'number' ? userId : null
}
