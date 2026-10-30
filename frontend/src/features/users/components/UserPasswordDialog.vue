<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { useForm } from '@/composables/useForm'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import {
  usePasswordConfirmation,
  usePasswordPolicy,
} from '@/features/security/composables/usePasswordPolicy'
import { HttpError } from '@/services/http'
import { compose, required } from '@/utils/validators'
import { useChangeUserPasswordMutation } from '@/features/users/composables/useUsers'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The target user's id. */
  userId: number
  /** The target user's username, shown in the dialog copy. */
  username: string
  /** The target user's access type, so the right length policy is enforced. */
  accessType: string
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const mutation = useChangeUserPasswordMutation()
// The policy follows the target user's access tier.
const { hint: passwordHint, validate: validatePassword } = usePasswordPolicy(() => props.accessType)

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
  if (formValues.password !== formValues.confirm) {
    return
  }
  try {
    await mutation.mutateAsync({ userId: props.userId, password: formValues.password })
    emit('success', t('settings.users.password.success'))
    open.value = false
  } catch (error) {
    if (error instanceof HttpError && (error.status === 400 || error.status === 422)) {
      emit('error', t('app.password.invalid'))
    } else {
      emit('error', t('settings.users.password.error'))
    }
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<PasswordFormValues>({
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

// Reset to a clean form each time the dialog opens.
watch(open, (isOpen) => {
  if (isOpen) {
    reset()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.users.password.title')"
    :description="t('settings.users.password.description', { username })"
    :submit-label="t('settings.users.password.submit')"
    :cancel-label="t('settings.users.password.cancel')"
    :close-label="t('settings.users.password.close')"
    :submitting="isSubmitting"
    :can-submit="isValid && passwordsMatch"
    @submit="handleSubmit"
  >
    <div class="flex flex-col gap-3">
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
            :disabled="isSubmitting"
            @blur="handleBlur('password')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.users.password.confirmLabel')"
        :placeholder="t('settings.users.password.confirmLabel')"
        :error="confirmError"
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
            :disabled="isSubmitting"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
