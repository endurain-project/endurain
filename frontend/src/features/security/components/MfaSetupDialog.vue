<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { IdpReauth, MfaSetup } from '@/features/security/types'

import IdpStepUpSection from '@/features/security/components/IdpStepUpSection.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { FormDialog } from '@/components/ui/form-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useEnableMfaMutation,
  useSetupMfaMutation,
} from '@/features/security/composables/useSecurity'

const open = defineModel<boolean>('open', { required: true })
// The identity-provider sign-in proof, used when the account has no password.
const reauth = defineModel<IdpReauth | null>('reauth', { default: null })

const props = defineProps<{
  /** Whether a step-up password is required; when not, the account signs in again with its identity provider. */
  requirePassword: boolean
}>()

const emit = defineEmits<{
  /** Enrolment succeeded; carries the one-time backup codes to display. */
  enabled: [codes: string[]]
  /** A setup or enable request failed; carries a user-facing message. */
  error: [message: string]
}>()

const { t } = useI18n()

const setupMutation = useSetupMfaMutation()
const enableMutation = useEnableMfaMutation()

const setup = ref<MfaSetup | null>(null)
const code = ref('')
const password = ref('')

const canSubmit = computed(
  () =>
    setup.value !== null &&
    code.value.trim().length > 0 &&
    (!props.requirePassword || password.value.length > 0),
)

// Begin enrolment when the dialog opens (fetch the secret + QR), and reset on
// close. An account without a password signs in again with its identity
// provider first, so enrolment starts once that sign-in has returned. A setup
// failure closes the dialog with an error toast.
watch([open, reauth], async ([isOpen, proof]) => {
  if (!isOpen) {
    setup.value = null
    code.value = ''
    password.value = ''
    return
  }
  if (!props.requirePassword && !proof) {
    setup.value = null
    return
  }
  setup.value = null
  try {
    setup.value = await setupMutation.mutateAsync()
  } catch {
    emit('error', t('settings.security.mfa.setupError'))
    open.value = false
  }
})

/** Confirms enrolment with the first valid code, then hands back the backup codes. */
async function onSubmit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  try {
    const codes = await enableMutation.mutateAsync({
      mfaCode: code.value.trim(),
      currentPassword: props.requirePassword ? password.value : null,
      idpReauth: props.requirePassword ? null : reauth.value,
    })
    open.value = false
    emit('enabled', codes)
  } catch {
    emit('error', t('settings.security.mfa.enableError'))
  }
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.security.mfa.setupTitle')"
    :description="t('settings.security.mfa.setupDescription')"
    :submit-label="t('settings.security.mfa.enableSubmit')"
    :cancel-label="t('settings.security.cancel')"
    :close-label="t('settings.security.close')"
    :submitting="enableMutation.isPending.value"
    :can-submit="canSubmit"
    @submit="onSubmit"
  >
    <div class="flex flex-col gap-3">
      <IdpStepUpSection
        v-if="!requirePassword"
        v-model:reauth="reauth"
        action="mfa_enable"
        :disabled="enableMutation.isPending.value"
      />
      <div
        v-if="(requirePassword || reauth) && (setupMutation.isPending.value || !setup)"
        class="flex items-center justify-center py-10"
      >
        <LoaderCircle class="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
      </div>

      <template v-else-if="setup">
        <ol class="flex list-decimal flex-col gap-1.5 pl-5 text-body">
          <li>{{ t('settings.security.mfa.step1') }}</li>
          <li>{{ t('settings.security.mfa.step2') }}</li>
          <li>{{ t('settings.security.mfa.step3') }}</li>
        </ol>

        <div class="flex justify-center">
          <img
            :src="setup.qrCode"
            :alt="t('settings.security.mfa.qrAlt')"
            class="size-44 rounded-input border border-border bg-white p-2"
          />
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="mfa-secret">{{ t('settings.security.mfa.secret') }}</Label>
          <code
            id="mfa-secret"
            class="select-all break-all rounded-input border border-border bg-muted-foreground/10 px-3 py-2 font-mono text-sm"
          >
            {{ setup.secret }}
          </code>
        </div>

        <div v-if="requirePassword" class="flex flex-col gap-1.5">
          <Label for="mfa-enable-password">{{ t('settings.security.password.current') }}</Label>
          <PasswordInput
            id="mfa-enable-password"
            v-model="password"
            autocomplete="current-password"
            :disabled="enableMutation.isPending.value"
          />
        </div>

        <div class="flex flex-col gap-1.5">
          <Label for="mfa-enable-code">{{ t('settings.security.mfa.verificationCode') }}</Label>
          <Input
            id="mfa-enable-code"
            v-model="code"
            inputmode="numeric"
            autocomplete="one-time-code"
            :placeholder="t('settings.security.mfaCodePlaceholder')"
            :disabled="enableMutation.isPending.value"
            class="w-full"
          />
        </div>
      </template>
    </div>
  </FormDialog>
</template>
