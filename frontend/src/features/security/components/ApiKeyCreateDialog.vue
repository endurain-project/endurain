<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { ApiKeyCreateInput } from '@/features/security/types'

import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { FormDialog } from '@/components/ui/form-dialog'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { API_KEY_SCOPES } from '@/features/security/services/security'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** Whether a password is required (the account has a local password). */
    requirePassword: boolean
    /** Whether an MFA/backup code is required (MFA is enabled). */
    requireMfa?: boolean
    /** Whether the create request is in flight. */
    pending: boolean
  }>(),
  { requireMfa: true },
)

const emit = defineEmits<{
  submit: [input: ApiKeyCreateInput]
}>()

const { t } = useI18n()

const name = ref('')
const expiresAt = ref('')
const password = ref('')
const mfaCode = ref('')
const selectedScopes = ref<string[]>([])

/** Adds or removes a scope from the granted set. */
function toggleScope(scope: string, granted: boolean): void {
  selectedScopes.value = granted
    ? [...selectedScopes.value, scope]
    : selectedScopes.value.filter((value) => value !== scope)
}

/** The earliest selectable expiry: tomorrow (a key must outlive today). */
const minExpiry = computed(() => {
  // Local calendar, not UTC: reading the UTC day let a viewer at UTC+13 pick a
  // key already expiring today, and stopped one at UTC-11 picking tomorrow.
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  const year = tomorrow.getFullYear()
  const month = String(tomorrow.getMonth() + 1).padStart(2, '0')
  const day = String(tomorrow.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
})

const canSubmit = computed(
  () =>
    name.value.trim().length > 0 &&
    selectedScopes.value.length > 0 &&
    (!props.requirePassword || password.value.length > 0) &&
    (!props.requireMfa || mfaCode.value.trim().length > 0),
)

// Reset every field each time the dialog opens.
watch(open, (isOpen) => {
  if (isOpen) {
    name.value = ''
    expiresAt.value = ''
    password.value = ''
    mfaCode.value = ''
    selectedScopes.value = []
  }
})

/** Emits the collected input; the parent runs the create mutation. */
function onSubmit(): void {
  emit('submit', {
    name: name.value.trim(),
    scopes: selectedScopes.value,
    expiresAt: expiresAt.value || null,
    currentPassword: props.requirePassword ? password.value : null,
    mfaCode: props.requireMfa ? mfaCode.value.trim() : null,
  })
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('settings.security.apiKeys.createTitle')"
    :description="t('settings.security.apiKeys.createDescription')"
    :submit-label="t('settings.security.apiKeys.create')"
    :cancel-label="t('settings.security.cancel')"
    :close-label="t('settings.security.close')"
    :submitting="pending"
    :can-submit="canSubmit"
    @submit="onSubmit"
  >
    <div class="flex flex-col gap-3">
      <div class="flex flex-col gap-1.5">
        <Label for="apikey-name">{{ t('settings.security.apiKeys.name') }}</Label>
        <Input
          id="apikey-name"
          v-model="name"
          maxlength="100"
          :placeholder="t('settings.security.apiKeys.namePlaceholder')"
          :disabled="pending"
          class="w-full"
        />
      </div>

      <div class="flex flex-col gap-2">
        <Label>{{ t('settings.security.apiKeys.scopes') }}</Label>
        <Switch
          v-for="scope in API_KEY_SCOPES"
          :key="scope"
          :model-value="selectedScopes.includes(scope)"
          :disabled="pending"
          @update:model-value="(granted) => toggleScope(scope, granted)"
        >
          <span class="font-mono text-sm">{{ scope }}</span>
        </Switch>
        <p class="text-hint">{{ t('settings.security.apiKeys.scopesHint') }}</p>
      </div>

      <div class="flex flex-col gap-1.5">
        <Label for="apikey-expiry">{{ t('settings.security.apiKeys.expiry') }}</Label>
        <input
          id="apikey-expiry"
          v-model="expiresAt"
          type="date"
          :min="minExpiry"
          :disabled="pending"
          :class="inputFieldClass"
        />
        <p class="text-hint">{{ t('settings.security.apiKeys.expiryHint') }}</p>
      </div>

      <div v-if="requirePassword" class="flex flex-col gap-1.5">
        <Label for="apikey-password">{{ t('settings.security.password.current') }}</Label>
        <PasswordInput
          id="apikey-password"
          v-model="password"
          autocomplete="current-password"
          :disabled="pending"
        />
      </div>

      <div v-if="requireMfa" class="flex flex-col gap-1.5">
        <Label for="apikey-mfa">{{ t('settings.security.mfaCode') }}</Label>
        <Input
          id="apikey-mfa"
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
