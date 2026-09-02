<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { StravaClientInput } from '@/features/integrations/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Label } from '@/components/ui/label'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { toNumberOrNull } from '@/utils/number'

const open = defineModel<boolean>('open', { required: true })

defineProps<{
  /** Whether the connect flow is in flight (state + client + redirect). */
  pending: boolean
}>()

const emit = defineEmits<{
  submit: [input: StravaClientInput]
}>()

const { t } = useI18n()

// `<input type="number">` bound with `v-model` yields a `number` (or `''` when
// blank), so the raw ref is never guaranteed to be a string.
const clientId = ref<string | number>('')
const clientSecret = ref('')

const parsedClientId = computed(() => toNumberOrNull(clientId.value))

const canSubmit = computed(() => parsedClientId.value !== null && clientSecret.value.length > 0)

watch(open, (isOpen) => {
  if (isOpen) {
    clientId.value = ''
    clientSecret.value = ''
  }
})

function onSubmit(): void {
  if (parsedClientId.value === null) {
    return
  }
  emit('submit', { clientId: parsedClientId.value, clientSecret: clientSecret.value })
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.integrations.strava.connectTitle')"
    :description="t('settings.integrations.strava.connectDescription')"
    :submit-label="t('settings.integrations.strava.connect')"
    :cancel-label="t('settings.integrations.cancel')"
    :close-label="t('settings.integrations.close')"
    :submitting="pending"
    :can-submit="canSubmit"
    @submit="onSubmit"
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <Label for="strava-client-id">{{ t('settings.integrations.strava.clientId') }}</Label>
        <input
          id="strava-client-id"
          v-model="clientId"
          type="number"
          inputmode="numeric"
          :placeholder="t('settings.integrations.strava.clientIdPlaceholder')"
          :disabled="pending"
          :class="inputFieldClass"
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <Label for="strava-client-secret">
          {{ t('settings.integrations.strava.clientSecret') }}
        </Label>
        <PasswordInput
          id="strava-client-secret"
          v-model="clientSecret"
          name="strava-client-secret"
          autocomplete="off"
          :disabled="pending"
          :placeholder="t('settings.integrations.strava.clientSecret')"
        />
      </div>

      <p class="text-hint">{{ t('settings.integrations.strava.connectHint') }}</p>
    </div>
  </FormDialog>
</template>
