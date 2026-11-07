<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import { resendSignUpVerification } from '@/features/auth/services/signUp'
import { HttpError } from '@/services/http'
import { compose, email, required } from '@/utils/validators'

/** Form field shape backing the resend form. */
interface ResendValues {
  email: string
}

const { t } = useI18n()
const toasts = useToasts()

/**
 * Requests a new verification email. The backend answers the same for every
 * address, so success only means the request was accepted.
 *
 * @param formValues - Validated form values.
 */
async function submitForm(formValues: ResendValues): Promise<void> {
  try {
    await resendSignUpVerification({ email: formValues.email.trim().toLowerCase() })
    toasts.success(t('verifyEmail.resendSent'))
  } catch (error) {
    throw new Error(
      error instanceof HttpError && error.status === 429
        ? t('verifyEmail.resendTooManyAttempts')
        : t('verifyEmail.resendError'),
    )
  }
}

const { values, errors, isValid, isSubmitting, submitError, handleSubmit, handleBlur } =
  useForm<ResendValues>({
    initialValues: { email: '' },
    validators: {
      email: compose(required<string>(t('signup.requiredField')), email(t('signup.emailInvalid'))),
    },
    onSubmit: submitForm,
  })
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <h2 class="text-center text-card-heading">{{ t('verifyEmail.resendTitle') }}</h2>
    <p class="text-center text-body">{{ t('verifyEmail.resendBody') }}</p>

    <Alert v-if="submitError" kind="error">
      {{ submitError }}
    </Alert>

    <FormField :label="t('verifyEmail.resendEmail')" required :error="errors.email">
      <template #default="{ fieldId, describedBy, invalid }">
        <Input
          :id="fieldId"
          v-model="values.email"
          :aria-describedby="describedBy"
          :aria-invalid="invalid"
          name="email"
          type="email"
          autocomplete="email"
          required
          :disabled="isSubmitting"
          @blur="handleBlur('email')"
        />
      </template>
    </FormField>

    <Button type="submit" class="w-full" :disabled="!isValid || isSubmitting">
      <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
      <span>{{
        isSubmitting ? t('verifyEmail.resendSending') : t('verifyEmail.resendButton')
      }}</span>
    </Button>
  </form>
</template>
