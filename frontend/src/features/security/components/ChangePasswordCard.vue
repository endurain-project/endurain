<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import { usePublicServerSettings } from '@/features/config/composables/usePublicServerSettings'
import { HttpError } from '@/services/http'
import {
  buildPasswordRequirements,
  isValidPassword,
  resolvePasswordMinLength,
} from '@/utils/validation'
import { useChangePasswordMutation } from '@/features/security/composables/useSecurity'

const props = defineProps<{
  /** Whether the account has MFA enabled (gates the MFA-code field). */
  mfaEnabled: boolean
  /** The account's access type, so the right length policy is enforced. */
  accessType: string
}>()

const { t } = useI18n()
const toasts = useToasts()
const { serverSettings } = usePublicServerSettings()
const mutation = useChangePasswordMutation()

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const mfaCode = ref('')
const revokeOtherSessions = ref(false)

const requirements = computed(() =>
  buildPasswordRequirements(
    serverSettings.value.password_type,
    resolvePasswordMinLength(
      serverSettings.value.password_length_regular_users,
      serverSettings.value.password_length_admin_users,
      props.accessType,
    ),
  ),
)
const requirementsHint = computed(() =>
  requirements.value.requireUppercase
    ? t('settings.security.password.requirementsStrict', { length: requirements.value.minLength })
    : t('settings.security.password.requirementsLength', { length: requirements.value.minLength }),
)

// Only surface validation messages once the field has content (live, like the
// reset-password screen) so the form doesn't shout before the user has typed.
const showInvalid = computed(
  () => newPassword.value.length > 0 && !isValidPassword(newPassword.value, requirements.value),
)
const showMismatch = computed(
  () => confirmPassword.value.length > 0 && newPassword.value !== confirmPassword.value,
)

const canSubmit = computed(
  () =>
    currentPassword.value.length > 0 &&
    isValidPassword(newPassword.value, requirements.value) &&
    newPassword.value === confirmPassword.value &&
    (!props.mfaEnabled || mfaCode.value.trim().length > 0) &&
    !mutation.isPending.value,
)

/** Clears every field after a successful change. */
function resetForm(): void {
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  mfaCode.value = ''
  revokeOtherSessions.value = false
}

/** Submits the change-password request and reports the outcome. */
async function submit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  try {
    await mutation.mutateAsync({
      currentPassword: currentPassword.value,
      newPassword: newPassword.value,
      mfaCode: props.mfaEnabled ? mfaCode.value.trim() : null,
      revokeOtherSessions: revokeOtherSessions.value,
    })
    toasts.success(t('settings.security.password.success'))
    resetForm()
  } catch (error) {
    if (error instanceof HttpError && (error.status === 400 || error.status === 401)) {
      toasts.error(t('settings.security.password.invalidCredentials'))
    } else {
      toasts.error(t('settings.security.password.error'))
    }
  }
}
</script>

<template>
  <Card class="flex flex-col gap-3" as="form" novalidate @submit.prevent="submit">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.security.password.title') }}</h2>
      <p class="text-hint">{{ t('settings.security.password.subtitle') }}</p>
    </div>

    <div class="flex flex-col gap-1.5">
      <Label for="security-current-password">{{ t('settings.security.password.current') }}</Label>
      <PasswordInput
        id="security-current-password"
        v-model="currentPassword"
        autocomplete="current-password"
        :disabled="mutation.isPending.value"
      />
    </div>

    <div class="flex flex-col gap-1.5">
      <Label for="security-new-password">{{ t('settings.security.password.new') }}</Label>
      <PasswordInput
        id="security-new-password"
        v-model="newPassword"
        autocomplete="new-password"
        :disabled="mutation.isPending.value"
        :aria-invalid="showInvalid"
        aria-describedby="security-new-password-hint"
      />
      <p id="security-new-password-hint" :class="showInvalid ? 'text-field-error' : 'text-hint'">
        {{ requirementsHint }}
      </p>
    </div>

    <div class="flex flex-col gap-1.5">
      <Label for="security-confirm-password">{{ t('settings.security.password.confirm') }}</Label>
      <PasswordInput
        id="security-confirm-password"
        v-model="confirmPassword"
        autocomplete="new-password"
        :disabled="mutation.isPending.value"
        :aria-invalid="showMismatch"
        aria-describedby="security-confirm-password-error"
      />
      <p v-if="showMismatch" id="security-confirm-password-error" class="text-field-error">
        {{ t('settings.security.password.mismatch') }}
      </p>
    </div>

    <div v-if="mfaEnabled" class="flex flex-col gap-1.5">
      <Label for="security-password-mfa">{{ t('settings.security.password.mfaCode') }}</Label>
      <Input
        id="security-password-mfa"
        v-model="mfaCode"
        inputmode="numeric"
        autocomplete="one-time-code"
        :placeholder="t('settings.security.mfaCodePlaceholder')"
        :disabled="mutation.isPending.value"
        class="w-full"
      />
    </div>

    <Switch v-model="revokeOtherSessions" :disabled="mutation.isPending.value">
      {{ t('settings.security.password.revokeOthers') }}
    </Switch>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="!canSubmit">
        <LoaderCircle
          v-if="mutation.isPending.value"
          class="size-4 animate-spin"
          aria-hidden="true"
        />
        {{ t('settings.security.password.submit') }}
      </Button>
    </div>
  </Card>
</template>
