<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import { Button } from '@/components/ui/button'
import { FormDialog } from '@/components/ui/form-dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useToasts } from '@/composables/useToasts'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import {
  useGarminLinkStatusQuery,
  useLinkGarminMutation,
  useSubmitGarminMfaMutation,
} from '@/features/integrations/composables/useIntegrations'

const open = defineModel<boolean>('open', { required: true })

const { t } = useI18n()
const toasts = useToasts()

const username = ref('')
const password = ref('')
const isCn = ref(false)
const mfaCode = ref('')
// The backend asks for an MFA code by reporting `mfa_required` on the link status we poll,
// so the prompt never depends on a realtime push arriving.
const mfaRequired = ref(false)
// True from the moment the MFA code is submitted until the link attempt finishes — the
// `/mfa` POST itself returns instantly, so the button must track the link, not that drop.
const isVerifyingMfa = ref(false)
// True while a started link attempt is being followed to its outcome.
const linking = ref(false)

const linkMutation = useLinkGarminMutation()
const mfaMutation = useSubmitGarminMfaMutation()
const statusQuery = useGarminLinkStatusQuery(linking)

/** Whether the credentials are locked: the start request or the background login is running. */
const busy = computed(() => linkMutation.isPending.value || linking.value)

const canSubmit = computed(() => username.value.trim().length > 0 && password.value.length > 0)

function reset(): void {
  username.value = ''
  password.value = ''
  isCn.value = false
  mfaCode.value = ''
  mfaRequired.value = false
  isVerifyingMfa.value = false
  linking.value = false
}

/** Ends the attempt on screen so the credentials can be corrected and resubmitted. */
function stopFollowing(): void {
  linking.value = false
  mfaRequired.value = false
  isVerifyingMfa.value = false
}

watch(open, (isOpen) => {
  if (isOpen) {
    reset()
  } else {
    // Closing stops following; the server finishes the attempt on its own.
    linking.value = false
  }
})

watch(
  () => statusQuery.data.value,
  (state) => {
    if (!state) {
      return
    }
    if (state.status === 'mfa_required') {
      mfaRequired.value = true
    } else if (state.status === 'completed') {
      stopFollowing()
      open.value = false
      toasts.success(t('settings.integrations.garmin.linkSuccess'))
    } else if (state.status === 'failed') {
      stopFollowing()
      toasts.error(
        state.reason === 'invalid_credentials'
          ? t('settings.integrations.garmin.invalidCredentials')
          : state.reason === 'incorrect_mfa'
            ? t('settings.integrations.garmin.mfaError')
            : t('settings.integrations.garmin.linkError'),
      )
    }
  },
)

// The status is gone (expired) or unreachable: stop waiting instead of polling forever.
watch(
  () => statusQuery.isError.value,
  (failed) => {
    if (failed) {
      stopFollowing()
      toasts.error(t('settings.integrations.garmin.linkError'))
    }
  },
)

/** Starts the link; the dialog then follows its status until it completes or fails. */
function onLogin(): void {
  linkMutation.mutate(
    { username: username.value.trim(), password: password.value, isCn: isCn.value },
    {
      onSuccess: () => {
        linking.value = true
      },
      onError: () => {
        toasts.error(t('settings.integrations.garmin.linkError'))
      },
    },
  )
}

/** Submits the MFA code the backend asked for; the attempt resumes on its own. */
function onSubmitMfa(): void {
  const code = mfaCode.value.trim()
  if (code.length === 0) {
    return
  }
  // Keep the button busy until the attempt resolves (success closes the dialog, failure
  // clears this in stopFollowing); the `/mfa` POST returns at once.
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
    :submitting="busy"
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
          :disabled="busy"
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
          :disabled="busy"
          :placeholder="t('settings.integrations.garmin.password')"
        />
      </div>

      <Switch v-model="isCn" :disabled="busy">
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
