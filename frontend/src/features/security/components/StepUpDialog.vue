<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { IdpReauth, StepUpAction, StepUpInput } from '@/features/security/types'
import type { StepUpPending } from '@/features/security/composables/useIdpStepUp'

import IdpStepUpSection from '@/features/security/components/IdpStepUpSection.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { FormDialog } from '@/components/ui/form-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const open = defineModel<boolean>('open', { required: true })
// The identity-provider sign-in proof, used when the account has no password.
const reauth = defineModel<IdpReauth | null>('reauth', { default: null })

const props = withDefaults(
  defineProps<{
    /** Dialog heading. */
    title: string
    /** Supporting copy below the title. */
    description: string
    /** Label for the confirm button. */
    confirmLabel: string
    /** Whether a password is required; when not, the account signs in again with its identity provider. */
    requirePassword: boolean
    /** The sensitive operation, sent when starting the identity-provider sign-in. */
    action: StepUpAction
    /** What to restore after the identity-provider round-trip; never a secret. */
    pendingContext?: StepUpPending
    /** The context the identity-provider round-trip brought back, which refills the form once. */
    restoredContext?: StepUpPending
    /** Whether an MFA/backup code is required (MFA is enabled). */
    requireMfa?: boolean
    /** Whether the confirming action is in flight. */
    pending: boolean
    /** Text the user must type exactly before confirming (for irreversible actions). */
    confirmPhrase?: string
    /** Whether the confirming action is destructive. */
    destructive?: boolean
    /** Whether the fields the parent adds through the default slot are valid. */
    extraValid?: boolean
  }>(),
  {
    requireMfa: true,
    pendingContext: () => ({}),
    restoredContext: undefined,
    confirmPhrase: undefined,
    destructive: false,
    extraValid: true,
  },
)

const emit = defineEmits<{
  confirm: [input: StepUpInput]
}>()

const { t } = useI18n()

const password = ref('')
const mfaCode = ref('')
const typedPhrase = ref('')

const canSubmit = computed(
  () =>
    props.extraValid &&
    (props.confirmPhrase === undefined || typedPhrase.value === props.confirmPhrase) &&
    (!props.requirePassword || password.value.length > 0) &&
    (props.requirePassword || reauth.value !== null) &&
    (!props.requireMfa || mfaCode.value.trim().length > 0),
)

// The confirmation phrase is not a secret, so the user does not retype it after signing in again with the
// identity provider: it travels with the pending context and comes back once, on the reopen that resumes it.
let restoredPhrase =
  typeof props.restoredContext?.typedPhrase === 'string' ? props.restoredContext.typedPhrase : ''
const sectionContext = computed<StepUpPending>(() =>
  props.confirmPhrase === undefined
    ? props.pendingContext
    : { ...props.pendingContext, typedPhrase: typedPhrase.value },
)

// Clear the fields each time the dialog opens.
watch(
  open,
  (isOpen) => {
    if (isOpen) {
      password.value = ''
      mfaCode.value = ''
      typedPhrase.value = restoredPhrase
      restoredPhrase = ''
    }
  },
  { immediate: true },
)

/** Emits the collected step-up credentials; the parent runs the action. */
function onSubmit(): void {
  emit('confirm', {
    currentPassword: props.requirePassword ? password.value : null,
    mfaCode: props.requireMfa ? mfaCode.value.trim() : null,
    idpReauth: props.requirePassword ? null : reauth.value,
  })
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="title"
    :description="description"
    :submit-label="confirmLabel"
    :cancel-label="t('settings.security.cancel')"
    :close-label="t('settings.security.close')"
    :submitting="pending"
    :can-submit="canSubmit"
    :destructive="destructive"
    @submit="onSubmit"
  >
    <div class="flex flex-col gap-3">
      <slot />
      <div v-if="confirmPhrase !== undefined" class="flex flex-col gap-1.5">
        <Label for="stepup-confirm-phrase">
          {{ t('settings.security.confirmPhrase', { phrase: confirmPhrase }) }}
        </Label>
        <Input
          id="stepup-confirm-phrase"
          v-model="typedPhrase"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          :disabled="pending"
          class="w-full"
        />
      </div>
      <IdpStepUpSection
        v-if="!requirePassword"
        v-model:reauth="reauth"
        :action="action"
        :pending-context="sectionContext"
        :disabled="pending"
      />
      <div v-if="requirePassword" class="flex flex-col gap-1.5">
        <Label for="stepup-password">{{ t('settings.security.password.current') }}</Label>
        <PasswordInput
          id="stepup-password"
          v-model="password"
          autocomplete="current-password"
          :disabled="pending"
        />
      </div>
      <div v-if="requireMfa && (requirePassword || reauth)" class="flex flex-col gap-1.5">
        <Label for="stepup-mfa">{{ t('settings.security.mfaCode') }}</Label>
        <Input
          id="stepup-mfa"
          v-model="mfaCode"
          inputmode="numeric"
          autocomplete="one-time-code"
          :placeholder="t('settings.security.mfaCodePlaceholder')"
          :disabled="pending"
          class="w-full"
        />
      </div>
    </div>
  </FormDialog>
</template>
