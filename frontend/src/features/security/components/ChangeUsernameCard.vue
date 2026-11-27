<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle, UserPen } from '@lucide/vue'

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
import { applyServerFieldErrors } from '@/services/fieldErrors'
import { isProblem } from '@/services/problems'
import { normalizeMfaCode } from '@/features/auth/utils/mfaCode'
import {
  isStepUpFailed,
  isStepUpLocked,
  useIdpReauthChallenge,
} from '@/features/security/composables/useIdpStepUp'
import { useChangeUsernameMutation } from '@/features/security/composables/useSecurity'

/** Letters, digits, dots, hyphens and underscores, as the server accepts. */
const USERNAME_PATTERN = /^[a-zA-Z0-9._-]+$/

const props = defineProps<{
  /** The account's current username. */
  username: string
  /** Whether the account has a local password (gates the step-up password field). */
  hasLocalPassword: boolean
  /** Whether MFA is enabled (gates the step-up MFA-code field). */
  mfaEnabled: boolean
  /** The identity-provider sign-in the browser just returned from, if any. */
  resume: IdpStepUpResume | null
}>()

const { t } = useI18n()
const toasts = useToasts()
const changeMutation = useChangeUsernameMutation()
const handleIdpChallenge = useIdpReauthChallenge()

const newUsername = ref('')
const currentPassword = ref('')
const mfaCode = ref('')
const revokeOtherSessions = ref(true)
// The server's refusal of the username, shown under the field until it is edited.
const usernameServerError = ref<string | null>(null)
watch(newUsername, () => {
  usernameServerError.value = null
})

// The new username is typed after the identity-provider sign-in and never stored; the sessions switch is not
// a secret, so it survives the round-trip.
const idpReauth = ref<IdpReauth | null>(null)
const pendingContext = computed(() => ({ revokeOtherSessions: revokeOtherSessions.value }))
onMounted(() => {
  if (props.resume?.action === 'username_change') {
    idpReauth.value = props.resume.reauth
    revokeOtherSessions.value = props.resume.pending.revokeOtherSessions === true
  }
})

// The server stores usernames in lower case, so a change of case alone is not a change.
const trimmedUsername = computed(() => newUsername.value.trim())
const isUsernameValid = computed(() => USERNAME_PATTERN.test(trimmedUsername.value))
const showInvalid = computed(() => trimmedUsername.value.length > 0 && !isUsernameValid.value)
const isCurrentUsername = computed(
  () => trimmedUsername.value.toLowerCase() === props.username.toLowerCase(),
)

const canSubmit = computed(
  () =>
    isUsernameValid.value &&
    !isCurrentUsername.value &&
    (!props.hasLocalPassword || currentPassword.value.length > 0) &&
    (props.hasLocalPassword || idpReauth.value !== null) &&
    (!props.mfaEnabled || mfaCode.value.trim().length > 0) &&
    !changeMutation.isPending.value,
)

/** Clears every field after a successful change. */
function resetForm(): void {
  newUsername.value = ''
  currentPassword.value = ''
  mfaCode.value = ''
  revokeOtherSessions.value = true
  idpReauth.value = null
}

/** Changes the username after step-up; it applies at once. */
function submit(): void {
  if (!canSubmit.value) {
    return
  }
  changeMutation.mutate(
    {
      username: trimmedUsername.value,
      stepUp: {
        currentPassword: props.hasLocalPassword ? currentPassword.value : null,
        mfaCode: props.mfaEnabled ? normalizeMfaCode(mfaCode.value) : null,
        idpReauth: props.hasLocalPassword ? null : idpReauth.value,
      },
      revokeOtherSessions: revokeOtherSessions.value,
    },
    {
      onSuccess: () => {
        toasts.success(t('settings.security.username.success'))
        resetForm()
      },
      onError: (error) => {
        if (handleIdpChallenge(error)) {
          return
        }
        if (
          applyServerFieldErrors<{ username: string }>(
            error,
            (fieldErrors) => {
              usernameServerError.value = fieldErrors.username ?? null
            },
            t,
            ['username'],
          )
        ) {
          return
        }
        if (isProblem(error, 'conflict')) {
          toasts.error(t('settings.security.username.conflict'))
        } else if (isStepUpLocked(error)) {
          toasts.error(t('settings.security.stepUp.tooManyAttempts'))
        } else if (isStepUpFailed(error)) {
          toasts.error(t('settings.security.linked.invalidCredentials'))
        } else {
          toasts.error(t('settings.security.username.error'))
        }
      },
    },
  )
}
</script>

<template>
  <Card class="flex flex-col gap-3" as="form" novalidate @submit.prevent="submit">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.security.username.title') }}</h2>
      <p class="text-hint">{{ t('settings.security.username.subtitle') }}</p>
    </div>

    <div class="flex flex-col gap-1.5">
      <Label for="security-current-username">{{ t('settings.security.username.current') }}</Label>
      <Input id="security-current-username" :model-value="props.username" disabled readonly />
    </div>

    <IdpStepUpSection
      v-if="!hasLocalPassword"
      v-model:reauth="idpReauth"
      action="username_change"
      :pending-context="pendingContext"
      :disabled="changeMutation.isPending.value"
    />

    <div v-if="hasLocalPassword || idpReauth" class="flex flex-col gap-1.5">
      <Label for="security-new-username">{{ t('settings.security.username.new') }}</Label>
      <Input
        id="security-new-username"
        v-model="newUsername"
        maxlength="250"
        autocomplete="username"
        :aria-invalid="showInvalid || usernameServerError !== null"
        :disabled="changeMutation.isPending.value"
        class="w-full"
      />
      <p v-if="showInvalid" class="text-hint text-destructive">
        {{ t('settings.users.form.usernameInvalid') }}
      </p>
      <p v-else-if="usernameServerError" class="text-hint text-destructive">
        {{ usernameServerError }}
      </p>
      <p v-else-if="isCurrentUsername" class="text-hint">
        {{ t('settings.security.username.sameAsCurrent') }}
      </p>
    </div>

    <div v-if="hasLocalPassword" class="flex flex-col gap-1.5">
      <Label for="security-username-password">{{ t('settings.security.password.current') }}</Label>
      <PasswordInput
        id="security-username-password"
        v-model="currentPassword"
        autocomplete="current-password"
        :disabled="changeMutation.isPending.value"
      />
    </div>

    <div v-if="mfaEnabled && (hasLocalPassword || idpReauth)" class="flex flex-col gap-1.5">
      <Label for="security-username-mfa">{{ t('settings.security.mfaCode') }}</Label>
      <Input
        id="security-username-mfa"
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
        <UserPen v-else class="size-4" aria-hidden="true" />
        <span>{{ t('settings.security.username.action') }}</span>
      </Button>
    </div>
  </Card>
</template>
