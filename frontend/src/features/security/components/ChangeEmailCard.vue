<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle, Mail, RefreshCw, X } from '@lucide/vue'

import type { IdpReauth } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import IdpStepUpSection from '@/features/security/components/IdpStepUpSection.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import { HttpError } from '@/services/http'
import { useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import {
  useCancelEmailChangeMutation,
  useChangeEmailMutation,
  useResendEmailChangeMutation,
} from '@/features/security/composables/useSecurity'
import { formatMediumDateTime } from '@/utils/datetime'
import { isValidEmail } from '@/utils/validation'

const props = defineProps<{
  /** The account's current email address. */
  email: string
  /** The address awaiting confirmation, or `null` when no change is pending. */
  pendingEmail: string | null
  /** When the pending address's confirmation link expires, or `null`. */
  pendingEmailExpiresAt: string | null
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t, locale } = useI18n()
const toasts = useToasts()
const changeMutation = useChangeEmailMutation()
const resendMutation = useResendEmailChangeMutation()
const cancelMutation = useCancelEmailChangeMutation()
const handleIdpChallenge = useIdpReauthChallenge()

const newEmail = ref('')
const currentPassword = ref('')
const mfaCode = ref('')
const revokeOtherSessions = ref(false)

// The new address is typed after the identity-provider sign-in and never stored; the sessions switch is not
// a secret, so it survives the round-trip.
const idpReauth = ref<IdpReauth | null>(null)
const pendingContext = computed(() => ({ revokeOtherSessions: revokeOtherSessions.value }))
onMounted(() => {
  if (props.resume?.action === 'email_change') {
    idpReauth.value = props.resume.reauth
    revokeOtherSessions.value = props.resume.pending.revokeOtherSessions === true
  }
})

const trimmedEmail = computed(() => newEmail.value.trim())
const isEmailValid = computed(() => isValidEmail(trimmedEmail.value))
const showInvalid = computed(() => trimmedEmail.value.length > 0 && !isEmailValid.value)
// The current address is not a change; a pending change is dropped with its own Cancel button.
const isCurrentEmail = computed(
  () => trimmedEmail.value.toLowerCase() === props.email.toLowerCase(),
)

const canSubmit = computed(
  () =>
    isEmailValid.value &&
    !isCurrentEmail.value &&
    (!props.hasLocalPassword || currentPassword.value.length > 0) &&
    (props.hasLocalPassword || idpReauth.value !== null) &&
    (!props.mfaEnabled || mfaCode.value.trim().length > 0) &&
    !changeMutation.isPending.value,
)

/** Clears every field after a successful change. */
function resetForm(): void {
  newEmail.value = ''
  currentPassword.value = ''
  mfaCode.value = ''
  revokeOtherSessions.value = false
  idpReauth.value = null
}

/** Asks for a new confirmation link for the pending address. */
function resend(): void {
  resendMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('settings.security.email.resendSuccess')),
    onError: () => toasts.error(t('settings.security.email.resendError')),
  })
}

/** Drops the pending address, keeping the current one. */
function cancelPending(): void {
  cancelMutation.mutate(undefined, {
    onSuccess: () => toasts.success(t('settings.security.email.cancelSuccess')),
    onError: () => toasts.error(t('settings.security.email.cancelError')),
  })
}

/** Requests the email change after step-up; the new address applies once its link is followed. */
function submit(): void {
  if (!canSubmit.value) {
    return
  }
  changeMutation.mutate(
    {
      email: trimmedEmail.value,
      stepUp: {
        currentPassword: props.hasLocalPassword ? currentPassword.value : null,
        mfaCode: props.mfaEnabled ? mfaCode.value.trim() : null,
        idpReauth: props.hasLocalPassword ? null : idpReauth.value,
      },
      revokeOtherSessions: revokeOtherSessions.value,
    },
    {
      onSuccess: (pending) => {
        // Without outgoing mail the server applies the address at once, so no link was sent.
        toasts.success(
          t(pending ? 'settings.security.email.success' : 'settings.security.email.appliedSuccess'),
        )
        resetForm()
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (error instanceof HttpError && error.status === 409) {
          toasts.error(t('settings.security.email.conflict'))
        } else if (error instanceof HttpError && error.status === 401) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
        } else {
          toasts.error(t('settings.security.email.error'))
        }
      },
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3" as="form" novalidate @submit.prevent="submit">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.security.email.title') }}</h2>
      <p class="text-hint">{{ t('settings.security.email.subtitle') }}</p>
    </div>

    <div class="flex flex-col gap-1.5">
      <Label for="security-current-email">{{ t('settings.security.email.current') }}</Label>
      <Input
        id="security-current-email"
        :model-value="props.email"
        type="email"
        disabled
        readonly
      />
    </div>

    <div
      v-if="props.pendingEmail"
      class="flex flex-col gap-2 rounded-input border border-border p-3"
      role="status"
    >
      <p class="text-body">
        {{ t('settings.security.email.pending', { email: props.pendingEmail }) }}
      </p>
      <p v-if="props.pendingEmailExpiresAt" class="text-hint">
        {{
          t('settings.security.email.pendingExpires', {
            date: formatMediumDateTime(props.pendingEmailExpiresAt, locale),
          })
        }}
      </p>
      <div class="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          :disabled="resendMutation.isPending.value || cancelMutation.isPending.value"
          @click="resend"
        >
          <LoaderCircle
            v-if="resendMutation.isPending.value"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          <RefreshCw v-else class="size-4" aria-hidden="true" />
          <span>{{ t('settings.security.email.resend') }}</span>
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          :disabled="resendMutation.isPending.value || cancelMutation.isPending.value"
          @click="cancelPending"
        >
          <LoaderCircle
            v-if="cancelMutation.isPending.value"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          <X v-else class="size-4" aria-hidden="true" />
          <span>{{ t('settings.security.email.cancel') }}</span>
        </Button>
      </div>
    </div>

    <IdpStepUpSection
      v-if="!hasLocalPassword"
      v-model:reauth="idpReauth"
      action="email_change"
      :pending-context="pendingContext"
      :disabled="changeMutation.isPending.value"
    />

    <div v-if="hasLocalPassword || idpReauth" class="flex flex-col gap-1.5">
      <Label for="security-new-email">{{ t('settings.security.email.new') }}</Label>
      <Input
        id="security-new-email"
        v-model="newEmail"
        type="email"
        maxlength="250"
        autocomplete="email"
        :aria-invalid="showInvalid"
        :disabled="changeMutation.isPending.value"
        class="w-full"
      />
      <p v-if="showInvalid" class="text-hint text-destructive">
        {{ t('settings.security.email.invalid') }}
      </p>
      <p v-else-if="isCurrentEmail" class="text-hint">
        {{ t('settings.security.email.sameAsCurrent') }}
      </p>
    </div>

    <div v-if="hasLocalPassword" class="flex flex-col gap-1.5">
      <Label for="security-email-password">{{ t('settings.security.password.current') }}</Label>
      <PasswordInput
        id="security-email-password"
        v-model="currentPassword"
        autocomplete="current-password"
        :disabled="changeMutation.isPending.value"
      />
    </div>

    <div v-if="mfaEnabled && (hasLocalPassword || idpReauth)" class="flex flex-col gap-1.5">
      <Label for="security-email-mfa">{{ t('settings.security.mfaCode') }}</Label>
      <Input
        id="security-email-mfa"
        v-model="mfaCode"
        inputmode="numeric"
        autocomplete="one-time-code"
        :placeholder="t('settings.security.mfaCodePlaceholder')"
        :disabled="changeMutation.isPending.value"
        class="w-full"
      />
    </div>

    <Switch v-model="revokeOtherSessions" :disabled="changeMutation.isPending.value">
      {{ t('settings.security.password.revokeOthers') }}
    </Switch>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="!canSubmit">
        <LoaderCircle
          v-if="changeMutation.isPending.value"
          class="size-4 animate-spin"
          aria-hidden="true"
        />
        <Mail v-else class="size-4" aria-hidden="true" />
        <span>{{ t('settings.security.email.action') }}</span>
      </Button>
    </div>
  </Card>
</template>
