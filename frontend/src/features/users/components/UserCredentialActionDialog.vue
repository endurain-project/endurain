<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { IdpReauth, StepUpAction, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import {
  useRequireUserPasswordChangeMutation,
  useResetUserMfaMutation,
} from '@/features/users/composables/useUsers'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The target user's id. */
  userId: number
  /** The target user's username, shown in the dialog copy. */
  username: string
  /** `mfa-reset` removes the user's MFA; `password-change` makes them choose a new password. */
  variant: 'mfa-reset' | 'password-change'
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()
const resetMfaMutation = useResetUserMfaMutation()
const requirePasswordChangeMutation = useRequireUserPasswordChangeMutation()
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

const idpReauth = ref<IdpReauth | null>(null)

const isMfaReset = computed(() => props.variant === 'mfa-reset')
const action = computed<StepUpAction>(() =>
  isMfaReset.value ? 'admin_mfa_reset' : 'admin_credential_change_require',
)
const mutation = computed(() =>
  isMfaReset.value ? resetMfaMutation : requirePasswordChangeMutation,
)
const copyKey = computed(() =>
  isMfaReset.value ? 'settings.users.mfaReset' : 'settings.users.requirePasswordChange',
)

// Reopens the dialog once the identity-provider sign-in returns for this user and this action.
useResumeOnce(
  () => props.resume,
  action.value,
  (pending) => pending.userId === props.userId,
  (resume) => {
    idpReauth.value = resume.reauth
    open.value = true
  },
)

/** Runs the action with the administrator's step-up; the dialog stays open on a refused step-up. */
function onConfirm(stepUp: StepUpInput): void {
  mutation.value.mutate(
    { userId: props.userId, stepUp },
    {
      onSuccess: () => {
        open.value = false
        toasts.success(t(`${copyKey.value}.success`))
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
          return
        }
        // The only 409 on either route is the fixed cause: MFA is not on, or there is no local password.
        const refused = error instanceof HttpError && error.status === 409
        toasts.error(t(refused ? `${copyKey.value}.refused` : `${copyKey.value}.error`))
      },
    },
  )
}
</script>

<template>
  <StepUpDialog
    v-model:open="open"
    v-model:reauth="idpReauth"
    :action="action"
    :title="t(`${copyKey}.title`)"
    :description="t(`${copyKey}.description`, { username })"
    :confirm-label="t(`${copyKey}.confirm`)"
    :require-password="requirePassword"
    :require-mfa="requireMfa"
    :pending-context="{ userId }"
    destructive
    :pending="mutation.isPending.value"
    @confirm="onConfirm"
  />
</template>
