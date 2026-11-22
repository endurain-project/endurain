<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { useForm } from '@/composables/useForm'
import { isProblem, retryWaitMessage } from '@/services/problems'
import { requestPasswordReset } from '@/features/auth/services/passwordReset'
import { compose, email, required } from '@/utils/validators'

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

interface ForgotPasswordFormValues {
  email: string
}

/**
 * Requests a password reset email, surfacing the outcome to the parent and
 * closing the dialog on success. Field validation is handled inline by
 * `useForm`; only backend failures are emitted to the parent for a toast.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: ForgotPasswordFormValues): Promise<void> {
  try {
    await requestPasswordReset({ email: values.email.trim() })
    open.value = false
    emit('success', t('login.forgotPasswordRequestSuccess'))
  } catch (error) {
    const wait = retryWaitMessage(error, t)
    if (wait !== null) {
      emit('error', wait)
    } else if (isProblem(error, 'service-unavailable')) {
      emit('error', t('login.forgotPasswordEmailNotConfigured'))
    } else {
      emit('error', t('login.forgotPasswordRequestError'))
    }
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<ForgotPasswordFormValues>({
    initialValues: { email: '' },
    validators: {
      email: compose(
        required<string>(t('login.forgotPasswordEmailRequired')),
        email(t('login.forgotPasswordEmailRequired')),
      ),
    },
    onSubmit: submitForm,
  })

// Reset the field whenever the dialog closes so reopening starts clean.
watch(open, (isOpen) => {
  if (!isOpen) {
    reset()
  }
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent :close-label="t('login.closeForgotPassword')">
      <form novalidate @submit.prevent="handleSubmit">
        <DialogHeader>
          <DialogTitle>{{ t('login.forgotPasswordModalTitle') }}</DialogTitle>
          <DialogDescription>{{ t('login.forgotPasswordHelp') }}</DialogDescription>
        </DialogHeader>

        <FormField class="mt-4" :label="t('login.forgotPasswordEmail')" :error="errors.email">
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

        <DialogFooter class="mt-4">
          <Button type="button" variant="ghost" :disabled="isSubmitting" @click="open = false">
            {{ t('login.cancel') }}
          </Button>
          <Button type="submit" :disabled="isSubmitting || !isValid">
            <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
            <span>{{ t('login.forgotPasswordSubmit') }}</span>
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
