<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type { MailSettings, MailSettingsFormValues } from '@/features/serverSettings/types'
import type { IdpReauth, StepUpInput } from '@/features/security/types'
import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { Validator } from '@/utils/validators'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import EnvManagedNotice from '@/features/serverSettings/components/EnvManagedNotice.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'
import { useMailStepUpResume } from '@/features/serverSettings/composables/useMailStepUpResume'
import { useUpdateMailSettingsMutation } from '@/features/serverSettings/composables/useServerSettings'
import { isStepUpFailed, useIdpReauthChallenge } from '@/features/security/composables/useIdpStepUp'
import { useAdminStepUp, useResumeOnce } from '@/features/security/composables/useAdminStepUp'
import { HttpError } from '@/services/http'

const props = defineProps<{
  /** The loaded mail settings; seeds the form (the parent mounts this only after load). */
  settings: MailSettings
}>()

const emit = defineEmits<{
  /** Whether the form holds unsaved edits; fires whenever that changes. */
  dirtyChange: [dirty: boolean]
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdateMailSettingsMutation()
const handleIdpChallenge = useIdpReauthChallenge()
const { requirePassword, requireMfa } = useAdminStepUp()

// Every save needs the administrator's own step-up, collected by a dialog over the form.
const isStepUpOpen = ref(false)
const idpReauth = ref<IdpReauth | null>(null)
const pendingResume = useMailStepUpResume()

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
  return name ? t('settings.server.envLocked', { name }) : undefined
}

/**
 * The form values that survive the identity-provider sign-in. The password is left out, so it never
 * reaches storage; `passwordTyped` tells the resumed form that the administrator has to enter it again.
 *
 * @returns The draft entries and whether a password was being set.
 */
function draftValues(): Record<string, unknown> {
  const draft: Record<string, unknown> = { ...values }
  delete draft.password
  return { ...draft, passwordTyped: values.password !== '' }
}

/**
 * Keeps the stored draft entries that have the type of the matching form field, except the password.
 *
 * @param raw - The draft stored when the sign-in started.
 * @returns The entries that can be applied to the form.
 */
function pickDraft(raw: unknown): Partial<MailSettingsFormValues> {
  const stored: Record<string, unknown> = typeof raw === 'object' && raw !== null ? { ...raw } : {}
  const picked: Record<string, unknown> = {}
  for (const [key, base] of Object.entries(toFormValues(props.settings))) {
    if (key !== 'password' && typeof stored[key] === typeof base) {
      picked[key] = stored[key]
    }
  }
  return picked as Partial<MailSettingsFormValues>
}

/**
 * Restores the draft and the sign-in proof. A password the administrator was setting is not stored, so then
 * the form waits for it to be entered again instead of saving without it.
 *
 * @param resume - The sign-in the page returned from.
 */
function reopen(resume: IdpStepUpResume): void {
  pendingResume.value = null
  Object.assign(values, pickDraft(resume.pending.draft))
  idpReauth.value = resume.reauth
  const draft = resume.pending.draft
  const passwordTyped =
    typeof draft === 'object' &&
    draft !== null &&
    'passwordTyped' in draft &&
    draft.passwordTyped === true
  isStepUpOpen.value = !passwordTyped
}

/** Asks for the administrator's step-up before the validated form is saved. */
function submitForm(): void {
  isStepUpOpen.value = true
}

/**
 * Persists the mail settings with the administrator's step-up. Outcomes are surfaced as toasts; a rejection
 * by the backend (unusable configuration, env-managed field) shows its reason, and a refused step-up keeps
 * the dialog open for another try.
 *
 * @param stepUp - The administrator's step-up from the dialog.
 */
async function confirmSave(stepUp: StepUpInput): Promise<void> {
  // undefined keeps the stored password, null removes it, a string replaces it.
  const password = values.removePassword ? null : values.password || undefined
  try {
    await updateMutation.mutateAsync({
      settings: {
        version: props.settings.version,
        host: values.host.trim() || null,
        port: Number(values.port.trim()),
        security: values.security,
        username: values.username.trim() || null,
        fromAddress: values.fromAddress.trim() || null,
        password,
      },
      stepUp,
    })
    isStepUpOpen.value = false
    values.password = ''
    values.removePassword = false
    toasts.success(t('settings.server.email.saveSuccess'))
  } catch (error) {
    if (handleIdpChallenge(error)) {
      return
    }
    if (isStepUpFailed(error)) {
      toasts.error(t('settings.security.linked.invalidCredentials'))
      return
    }
    // The remaining failures are corrected in the form, so the step-up dialog gives way to it.
    isStepUpOpen.value = false
    // 412 is a refusal to overwrite: another admin saved since this form was loaded.
    if (error instanceof HttpError && error.status === 412) {
      toasts.error(t('settings.server.staleError'))
      return
    }
    const detail =
      error instanceof HttpError && typeof error.detail === 'string' ? error.detail : null
    toasts.error(detail ?? t('settings.server.email.saveError'))
  }
}

const { values, errors, isValid, isDirty, isSubmitting, handleSubmit, handleBlur } =
  useForm<MailSettingsFormValues>({
    initialValues: toFormValues(props.settings),
    validators: { port: portValidator(t('settings.server.email.portInvalid')) },
    onSubmit: submitForm,
  })

// The form and the step-up come back once the identity-provider sign-in returns for the mail settings.
useResumeOnce(
  () => pendingResume.value,
  'admin_mail_settings_edit',
  () => true,
  (resume) => reopen(resume),
)

const envNames = computed(() => [...new Set(Object.values(props.settings.envManaged))])

watch(isDirty, (dirty) => emit('dirtyChange', dirty))
// The parent rebuilds this form after a save; clear its flag with the old instance.
onBeforeUnmount(() => emit('dirtyChange', false))
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <EnvManagedNotice :names="envNames" />

    <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
      <FormField
        class="sm:col-span-2"
        data-setting="email-host"
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
        data-setting="email-port"
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

    <FormField
      data-setting="email-security"
      :label="t('settings.server.email.security')"
      :hint="envHint('security')"
    >
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
      <FormField
        data-setting="email-username"
        :label="t('settings.server.email.username')"
        :hint="envHint('username')"
      >
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

      <FormField
        data-setting="email-password"
        :label="t('settings.server.email.password')"
        :hint="envHint('password')"
      >
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
      data-setting="email-from-address"
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

  <StepUpDialog
    v-model:open="isStepUpOpen"
    v-model:reauth="idpReauth"
    action="admin_mail_settings_edit"
    :title="t('settings.server.email.stepUpTitle')"
    :description="t('settings.server.email.stepUpDescription')"
    :confirm-label="t('settings.server.email.save')"
    :require-password="requirePassword"
    :require-mfa="requireMfa"
    :pending-context="{ draft: draftValues() }"
    :pending="updateMutation.isPending.value"
    @confirm="confirmSave"
  />
</template>
