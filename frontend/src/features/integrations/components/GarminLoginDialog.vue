<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { FormDialog } from '@/components/ui/form-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import { useRealtime } from '@/composables/useRealtime'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { HttpError } from '@/services/http'
import {
  useLinkGarminMutation,
  useSubmitGarminMfaMutation,
} from '@/features/integrations/composables/useIntegrations'

const open = defineModel<boolean>('open', { required: true })

const { t } = useI18n()
const toasts = useToasts()
const realtime = useRealtime()

const username = ref('')
const password = ref('')
const isCn = ref(false)
const mfaCode = ref('')
// The Garmin login request stays pending while the backend waits for an MFA
// code, which it asks for over the realtime channel.
const mfaRequired = ref(false)
// True from the moment the MFA code is submitted until the (still-pending) link
// request resolves — the `/mfa` POST itself returns instantly, so the button
// must track the link completing, not that quick code drop.
const isVerifyingMfa = ref(false)

const linkMutation = useLinkGarminMutation()
const mfaMutation = useSubmitGarminMfaMutation()

let unsubscribe: (() => void) | null = null

const canSubmit = computed(() => username.value.trim().length > 0 && password.value.length > 0)

function reset(): void {
  username.value = ''
  password.value = ''
  isCn.value = false
  mfaCode.value = ''
  mfaRequired.value = false
  isVerifyingMfa.value = false
}

function stopListening(): void {
  unsubscribe?.()
  unsubscribe = null
}

watch(open, (isOpen) => {
  if (isOpen) {
    reset()
    unsubscribe = realtime.on('MFA_REQUIRED', () => {
      mfaRequired.value = true
    })
  } else {
    stopListening()
  }
})

onUnmounted(stopListening)

/** Starts the link; the request resolves once any required MFA code is supplied. */
function onLogin(): void {
  // Enter in a field or a double click must not start a second Garmin login:
  // each one makes Garmin send its own MFA code, so one of them always fails.
  if (linkMutation.isPending.value) {
    return
  }
  linkMutation.mutate(
    { username: username.value.trim(), password: password.value, isCn: isCn.value },
    {
      onSuccess: () => {
        open.value = false
        toasts.success(t('settings.integrations.garmin.linkSuccess'))
      },
      onError: (error) => {
        mfaRequired.value = false
        isVerifyingMfa.value = false
        toasts.error(
          error instanceof HttpError && error.status === 401
            ? t('settings.integrations.garmin.invalidCredentials')
            : t('settings.integrations.garmin.linkError'),
        )
      },
    },
  )
}

/** Submits the MFA code, which unblocks the pending login request. */
function onSubmitMfa(): void {
  const code = mfaCode.value.trim()
  if (code.length === 0) {
    return
  }
  // Keep the button busy until the link resolves (success closes the dialog,
  // failure clears this in the link's onError); the `/mfa` POST returns at once.
  isVerifyingMfa.value = true
  mfaMutation.mutate(code, {
    onError: () => {
      isVerifyingMfa.value = false
      toasts.error(t('settings.integrations.garmin.mfaError'))
    },
  })
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.integrations.garmin.connectTitle')"
    :description="t('settings.integrations.garmin.connectDescription')"
    :submit-label="t('settings.integrations.garmin.connect')"
    :cancel-label="t('settings.integrations.cancel')"
    :close-label="t('settings.integrations.close')"
    :submitting="linkMutation.isPending.value"
    :can-submit="canSubmit"
    @submit="onLogin"
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <Label for="garmin-username">{{ t('settings.integrations.garmin.username') }}</Label>
        <Input
          id="garmin-username"
          v-model="username"
          autocomplete="username"
          :disabled="linkMutation.isPending.value"
          :placeholder="t('settings.integrations.garmin.username')"
          class="w-full"
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <Label for="garmin-password">{{ t('settings.integrations.garmin.password') }}</Label>
        <PasswordInput
          id="garmin-password"
          v-model="password"
          name="current-password"
          autocomplete="current-password"
          :disabled="linkMutation.isPending.value"
          :placeholder="t('settings.integrations.garmin.password')"
        />
      </div>

      <Switch v-model="isCn" :disabled="linkMutation.isPending.value">
        {{ t('settings.integrations.garmin.isCn') }}
      </Switch>

      <div v-if="mfaRequired" class="flex flex-col gap-1.5">
        <Label for="garmin-mfa">{{ t('settings.integrations.garmin.mfaCode') }}</Label>
        <div class="flex gap-2">
          <Input
            id="garmin-mfa"
            v-model="mfaCode"
            inputmode="numeric"
            autocomplete="one-time-code"
            :disabled="isVerifyingMfa"
            class="w-full"
          />
          <Button
            type="button"
            :disabled="mfaCode.trim().length === 0 || isVerifyingMfa"
            @click="onSubmitMfa"
          >
            <LoaderCircle v-if="isVerifyingMfa" class="size-4 animate-spin" aria-hidden="true" />
            {{ t('settings.integrations.garmin.submitMfa') }}
          </Button>
        </div>
        <p class="text-hint">{{ t('settings.integrations.garmin.mfaHint') }}</p>
      </div>
    </div>
  </FormDialog>
</template>
