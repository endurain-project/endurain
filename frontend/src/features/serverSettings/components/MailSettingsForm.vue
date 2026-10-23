<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { MailSettings, MailSettingsFormValues } from '@/features/serverSettings/types'
import type { Validator } from '@/utils/validators'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import { useUpdateMailSettingsMutation } from '@/features/serverSettings/composables/useServerSettings'
import { HttpError } from '@/services/http'

const props = defineProps<{
  /** The loaded mail settings; seeds the form (the parent mounts this only after load). */
  settings: MailSettings
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdateMailSettingsMutation()

/** Highest valid TCP port. */
const MAX_PORT = 65535

/**
 * Projects the loaded settings onto the form. The password starts empty: the
 * backend never returns it, and an empty field keeps the stored one.
 *
 * @param settings - The loaded mail settings.
 * @returns The editable form values.
 */
function toFormValues(settings: MailSettings): MailSettingsFormValues {
  return {
    host: settings.host ?? '',
    port: String(settings.port),
    security: settings.security,
    username: settings.username ?? '',
    fromAddress: settings.fromAddress ?? '',
    password: '',
    removePassword: false,
  }
}

/**
 * Validates the port: a whole number from 1 to 65535.
 *
 * @param message - Error when the value is not a valid port.
 * @returns A validator for the port field.
 */
function portValidator(message: string): Validator<string> {
  return (value) => {
    const port = Number(value.trim())
    return value.trim() !== '' && Number.isInteger(port) && port >= 1 && port <= MAX_PORT
      ? null
      : message
  }
}

/**
 * The environment variable that sets a field, or undefined when it is editable.
 *
 * @param field - The backend field name (snake_case, as in `env_managed`).
 * @returns The variable name.
 */
function envVar(field: string): string | undefined {
  return props.settings.envManaged[field]
}

/**
 * The hint under an env-managed field, naming the variable that sets it.
 *
 * @param field - The backend field name.
 * @returns The hint, or undefined when the field is editable.
 */
function envHint(field: string): string | undefined {
  const name = envVar(field)
  return name ? t('settings.server.envManaged', { name }) : undefined
}

/**
 * Persists the mail settings. Outcomes are surfaced as toasts; a rejection by the
 * backend (unusable configuration, env-managed field) shows its reason.
 *
 * @param formValues - The validated form values.
 */
async function submitForm(formValues: MailSettingsFormValues): Promise<void> {
  // undefined keeps the stored password, null removes it, a string replaces it.
  const password = formValues.removePassword ? null : formValues.password || undefined
  try {
    await updateMutation.mutateAsync({
      host: formValues.host.trim() || null,
      port: Number(formValues.port.trim()),
      security: formValues.security,
      username: formValues.username.trim() || null,
      fromAddress: formValues.fromAddress.trim() || null,
      password,
    })
    values.password = ''
    values.removePassword = false
    toasts.success(t('settings.server.email.saveSuccess'))
  } catch (error) {
    const detail =
      error instanceof HttpError && typeof error.detail === 'string' ? error.detail : null
    toasts.error(detail ?? t('settings.server.email.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur } =
  useForm<MailSettingsFormValues>({
    initialValues: toFormValues(props.settings),
    validators: { port: portValidator(t('settings.server.email.portInvalid')) },
    onSubmit: submitForm,
  })

const allEnvManaged = computed(() => Object.keys(props.settings.envManaged).length > 0)
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <Alert v-if="allEnvManaged" kind="info">{{ t('settings.server.email.envManagedInfo') }}</Alert>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <FormField
        class="sm:col-span-2"
        :label="t('settings.server.email.host')"
        :hint="envHint('host') ?? t('settings.server.email.hostHint')"
      >
        <template #default="{ fieldId, describedBy }">
          <Input
            :id="fieldId"
            v-model="values.host"
            :aria-describedby="describedBy"
            type="text"
            maxlength="253"
            autocomplete="off"
            :disabled="isSubmitting || Boolean(envVar('host'))"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.server.email.port')"
        :hint="envHint('port')"
        :error="errors.port"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.port"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="text"
            inputmode="numeric"
            maxlength="5"
            :disabled="isSubmitting || Boolean(envVar('port'))"
            @blur="handleBlur('port')"
          />
        </template>
      </FormField>
    </div>

    <FormField :label="t('settings.server.email.security')" :hint="envHint('security')">
      <template #default="{ fieldId, describedBy }">
        <Select
          :id="fieldId"
          v-model="values.security"
          :aria-describedby="describedBy"
          :disabled="isSubmitting || Boolean(envVar('security'))"
        >
          <option value="starttls">{{ t('settings.server.email.securityStarttls') }}</option>
          <option value="ssl">{{ t('settings.server.email.securitySsl') }}</option>
          <option value="none">{{ t('settings.server.email.securityNone') }}</option>
        </Select>
      </template>
    </FormField>
    <Alert v-if="values.security === 'none'" kind="warning">
      {{ t('settings.server.email.securityNoneWarning') }}
    </Alert>

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField :label="t('settings.server.email.username')" :hint="envHint('username')">
        <template #default="{ fieldId, describedBy }">
          <Input
            :id="fieldId"
            v-model="values.username"
            :aria-describedby="describedBy"
            type="text"
            maxlength="320"
            autocomplete="off"
            :disabled="isSubmitting || Boolean(envVar('username'))"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.server.email.password')" :hint="envHint('password')">
        <template #default="{ fieldId, describedBy }">
          <Input
            :id="fieldId"
            v-model="values.password"
            :aria-describedby="describedBy"
            type="password"
            maxlength="256"
            autocomplete="new-password"
            :placeholder="settings.passwordSet ? t('settings.server.email.passwordStored') : ''"
            :disabled="isSubmitting || values.removePassword || Boolean(envVar('password'))"
          />
        </template>
      </FormField>
    </div>
    <Switch
      v-if="settings.passwordSet"
      v-model="values.removePassword"
      :disabled="isSubmitting || Boolean(envVar('password'))"
    >
      {{ t('settings.server.email.passwordRemove') }}
    </Switch>

    <FormField
      :label="t('settings.server.email.fromAddress')"
      :hint="envHint('from_address') ?? t('settings.server.email.fromAddressHint')"
    >
      <template #default="{ fieldId, describedBy }">
        <Input
          :id="fieldId"
          v-model="values.fromAddress"
          :aria-describedby="describedBy"
          type="text"
          inputmode="email"
          maxlength="320"
          autocomplete="off"
          :disabled="isSubmitting || Boolean(envVar('from_address'))"
        />
      </template>
    </FormField>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="!isValid || isSubmitting">
        <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
        {{ isSubmitting ? t('settings.server.saving') : t('settings.server.email.save') }}
      </Button>
    </div>
  </form>
</template>
