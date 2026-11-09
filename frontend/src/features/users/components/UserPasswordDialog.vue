<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { FormField } from '@/components/ui/form-field'
import { useForm } from '@/composables/useForm'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import PasswordStrengthMeter from '@/features/security/components/PasswordStrengthMeter.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { compose, required } from '@/utils/validators'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import { useChangeUserPasswordMutation } from '@/features/users/composables/useUsers'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The target user's id. */
  userId: number
  /** The target user's username, shown in the dialog copy. */
  username: string
  /** The target user's access type, so the right length policy is enforced. */
  accessType: string
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume?: IdpStepUpResume | null
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const mutation = useChangeUserPasswordMutation()
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

// The administrator's step-up, held between the dialog's confirmation and the form's submission.
const stepUp = ref<StepUpInput | null>(null)
const idpReauth = ref<IdpReauth | null>(null)

// Reopens the dialog once the identity-provider sign-in returns for this user. The new password is a
// secret and is never stored, so the administrator types it again.
useResumeOnce(
  () => props.resume ?? null,
  'admin_credential_reset',
  (pending) => Boolean(props.userId) && pending.userId === props.userId,
  (resume) => {
    idpReauth.value = resume.reauth
    open.value = true
  },
)
// The policy follows the target user's access tier.
const {
  hint: passwordHint,
  validate: validatePassword,
  policyError,
} = usePasswordPolicy(() => props.accessType)

/** Form shape: the new password plus its confirmation. */
interface PasswordFormValues {
  password: string
  confirm: string
}

/**
 * Sets the new password via the admin endpoint, emitting the outcome and
 * closing on success. The confirm field is validated reactively (see
 * `passwordsMatch`); this also guards against an Enter-key submit slipping
 * through on a mismatch.
 *
 * @param formValues - The validated form values.
 */
async function submitForm(formValues: PasswordFormValues): Promise<void> {
  if (formValues.password !== formValues.confirm || !stepUp.value) {
    return
  }
  try {
    await mutation.mutateAsync({
      userId: props.userId,
      password: formValues.password,
      stepUp: stepUp.value,
    })
    emit('success', t('settings.users.password.success'))
    open.value = false
  } catch (error) {
    const passwordProblem = policyError(error)
    if (handleIdpChallenge(error)) {
      return
    }
    if (isStepUpFailed(error)) {
      emit('error', t('settings.security.linked.invalidCredentials'))
    } else if (passwordProblem) {
      emit('error', passwordProblem)
    } else {
      emit('error', t('settings.users.password.error'))
    }
  }
}

const { values, errors, isValid, handleSubmit, handleBlur, reset } = useForm<PasswordFormValues>({
  initialValues: { password: '', confirm: '' },
  validators: {
    password: compose(required<string>(t('settings.users.password.required')), validatePassword),
  },
  onSubmit: submitForm,
})

const { matches: passwordsMatch, error: confirmError } = usePasswordConfirmation(
  () => values.password,
  () => values.confirm,
)

/** Submits the form with the administrator's step-up from the dialog. */
function onConfirm(input: StepUpInput): void {
  stepUp.value = input
  void handleSubmit()
}

// Reset to a clean form each time the dialog opens.
watch(open, (isOpen) => {
  if (isOpen) {
    reset()
  }
})
</script>

<template>
  <StepUpDialog
    v-model:open="open"
    v-model:reauth="idpReauth"
    action="admin_credential_reset"
    :title="t('settings.users.password.title')"
    :description="t('settings.users.password.description', { username })"
    :confirm-label="t('settings.users.password.submit')"
    :require-password="requirePassword"
    :require-mfa="requireMfa"
    :pending-context="{ userId }"
    :extra-valid="isValid && passwordsMatch"
    :pending="mutation.isPending.value"
    @confirm="onConfirm"
  >
    <FormField
      :label="t('settings.users.password.newLabel')"
      :placeholder="t('settings.users.password.newLabel')"
      :error="errors.password"
      :hint="passwordHint"
      required
    >
      <template #default="{ fieldId, describedBy, invalid, placeholder }">
        <PasswordInput
          :id="fieldId"
          v-model="values.password"
          :aria-describedby="describedBy"
          :aria-invalid="invalid"
          :placeholder="placeholder"
          name="new-password"
          autocomplete="new-password"
          :disabled="mutation.isPending.value"
          @blur="handleBlur('password')"
        />
        <PasswordStrengthMeter :password="values.password" :user-inputs="[username]" />
      </template>
    </FormField>

    <FormField
      :label="t('settings.users.password.confirmLabel')"
      :placeholder="t('settings.users.password.confirmLabel')"
      :error="confirmError"
      :hint="t('settings.users.form.mustChangePasswordHint')"
      required
    >
      <template #default="{ fieldId, describedBy, invalid, placeholder }">
        <PasswordInput
          :id="fieldId"
          v-model="values.confirm"
          :aria-describedby="describedBy"
          :aria-invalid="invalid"
          :placeholder="placeholder"
          name="confirm-password"
          autocomplete="new-password"
          :disabled="mutation.isPending.value"
        />
      </template>
    </FormField>
  </StepUpDialog>
</template>
