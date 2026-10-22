<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle } from '@lucide/vue'

import type {
  ServerSettings,
  ServerSettingsFormValues,
  TileMapsTemplate,
} from '@/features/serverSettings/types'
import type { Validator } from '@/utils/validators'

import { Alert } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { useToasts } from '@/composables/useToasts'
import { useUpdateServerSettingsMutation } from '@/features/serverSettings/composables/useServerSettings'

const props = defineProps<{
  /** The loaded server settings; seeds the form (the parent mounts this only after load). */
  settings: ServerSettings
  /** Available tile-server presets for the maps section. */
  templates: TileMapsTemplate[]
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdateServerSettingsMutation()

/** Records-per-page options offered in the list (mirrors v1). */
const NUM_RECORDS_OPTIONS = [5, 10, 25, 50, 100] as const
/** Minimum-length options for regular users: 8–20 (mirrors v1). */
const PASSWORD_REGULAR_LENGTHS = Array.from({ length: 13 }, (_, index) => index + 8)
/** Minimum-length options for admin users: 8–25 (mirrors v1). */
const PASSWORD_ADMIN_LENGTHS = Array.from({ length: 18 }, (_, index) => index + 8)
/** Sentinel id for the "custom" (manually edited) tile server. */
const CUSTOM_TEMPLATE = 'custom'
/** Placeholders every valid tile URL template must contain. */
const TILE_PLACEHOLDERS = ['{z}', '{x}', '{y}'] as const

/**
 * Projects the loaded settings onto the form-editable subset. `id` and
 * `loginPhotoSet` are intentionally excluded: they round-trip from the freshest
 * server state at save time, never from a stale form value. The tile API key starts
 * empty: the backend never returns it, and an empty field keeps the stored one.
 *
 * @param settings - The loaded server settings.
 * @returns The editable form values.
 */
function toFormValues(settings: ServerSettings): ServerSettingsFormValues {
  return {
    units: settings.units,
    currency: settings.currency,
    numRecordsPerPage: settings.numRecordsPerPage,
    publicShareableLinks: settings.publicShareableLinks,
    publicShareableLinksUserInfo: settings.publicShareableLinksUserInfo,
    signupEnabled: settings.signupEnabled,
    signupRequireAdminApproval: settings.signupRequireAdminApproval,
    signupRequireEmailVerification: settings.signupRequireEmailVerification,
    ssoEnabled: settings.ssoEnabled,
    localLoginEnabled: settings.localLoginEnabled,
    ssoAutoRedirect: settings.ssoAutoRedirect,
    tileserverUrl: settings.tileserverUrl,
    tileserverAttribution: settings.tileserverAttribution,
    tileserverApiKey: '',
    removeTileserverApiKey: false,
    tileserverRegenerateThumbnailsOnChange: settings.tileserverRegenerateThumbnailsOnChange,
    mapBackgroundColor: settings.mapBackgroundColor,
    passwordType: settings.passwordType,
    passwordLengthRegularUsers: settings.passwordLengthRegularUsers,
    passwordLengthAdminUsers: settings.passwordLengthAdminUsers,
  }
}

/**
 * Validates the tile URL template: non-empty and containing the `{z}/{x}/{y}`
 * placeholders. The backend enforces the full rule set (HTTPS, blocked
 * schemes) authoritatively; this is fast client feedback for the common case.
 *
 * @param requiredMessage - Error when the field is empty.
 * @param placeholderMessage - Error when a coordinate placeholder is missing.
 * @returns A validator for the tile URL field.
 */
function tileUrlValidator(requiredMessage: string, placeholderMessage: string): Validator<string> {
  return (value) => {
    const trimmed = value.trim()
    if (!trimmed) {
      return requiredMessage
    }
    return TILE_PLACEHOLDERS.every((placeholder) => trimmed.includes(placeholder))
      ? null
      : placeholderMessage
  }
}

/**
 * Finds the preset whose URL matches the given template, or the `custom`
 * sentinel when none does.
 *
 * @param url - The current tile URL template.
 * @returns The matching preset id, or `custom`.
 */
function detectTemplate(url: string): string {
  return (
    props.templates.find((template) => template.urlTemplate === url)?.templateId ?? CUSTOM_TEMPLATE
  )
}

/**
 * Persists the whole settings record, merging the form edits over the freshest
 * server state so `id` and `loginPhotoSet` round-trip untouched. Outcomes are
 * surfaced as toasts; the error is not rethrown, so no inline submit error
 * banner appears.
 *
 * @param formValues - The validated form values.
 */
async function submitForm(formValues: ServerSettingsFormValues): Promise<void> {
  const { tileserverApiKey, removeTileserverApiKey, ...editable } = formValues
  // undefined keeps the stored key, null removes it, a string replaces it.
  const apiKey = removeTileserverApiKey ? null : tileserverApiKey.trim() || undefined
  try {
    await updateMutation.mutateAsync({ ...props.settings, ...editable, tileserverApiKey: apiKey })
    toasts.success(t('settings.server.saveSuccess'))
  } catch {
    toasts.error(t('settings.server.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur } =
  useForm<ServerSettingsFormValues>({
    initialValues: toFormValues(props.settings),
    validators: {
      tileserverUrl: tileUrlValidator(
        t('settings.server.maps.urlRequired'),
        t('settings.server.maps.urlInvalid'),
      ),
    },
    onSubmit: submitForm,
  })

const selectedTemplate = ref(detectTemplate(props.settings.tileserverUrl))
const isCustomTemplate = computed(() => selectedTemplate.value === CUSTOM_TEMPLATE)
const selectedTemplateData = computed(
  () => props.templates.find((template) => template.templateId === selectedTemplate.value) ?? null,
)

// Applying a preset fills the URL/attribution/background and clears the API key
// (presets either embed it or need it configured elsewhere); the three fields
// are then read-only until the user switches back to "custom".
watch(selectedTemplate, (templateId) => {
  if (templateId === CUSTOM_TEMPLATE) {
    return
  }
  const template = props.templates.find((entry) => entry.templateId === templateId)
  if (!template) {
    return
  }
  values.tileserverUrl = template.urlTemplate
  values.tileserverAttribution = template.attribution
  values.tileserverApiKey = ''
  values.removeTileserverApiKey = props.settings.tileserverApiKeySet
  values.mapBackgroundColor = template.mapBackgroundColor
})
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <!-- General -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.general.title') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField :label="t('settings.server.general.units')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.units" :disabled="isSubmitting">
              <option value="metric">{{ t('settings.server.general.unitsMetric') }}</option>
              <option value="imperial">{{ t('settings.server.general.unitsImperial') }}</option>
            </Select>
          </template>
        </FormField>

        <FormField :label="t('settings.server.general.currency')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.currency" :disabled="isSubmitting">
              <option value="euro">{{ t('settings.server.general.currencyEuro') }}</option>
              <option value="dollar">{{ t('settings.server.general.currencyDollar') }}</option>
              <option value="pound">{{ t('settings.server.general.currencyPound') }}</option>
            </Select>
          </template>
        </FormField>

        <FormField :label="t('settings.server.general.numRecords')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.numRecordsPerPage" :disabled="isSubmitting">
              <option v-for="size in NUM_RECORDS_OPTIONS" :key="size" :value="size">
                {{ size }}
              </option>
            </Select>
          </template>
        </FormField>
      </div>
    </Card>

    <!-- Password policy -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.password.title') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField :label="t('settings.server.password.type')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.passwordType" :disabled="isSubmitting">
              <option value="strict">{{ t('settings.server.password.typeStrict') }}</option>
              <option value="length_only">
                {{ t('settings.server.password.typeLengthOnly') }}
              </option>
            </Select>
          </template>
        </FormField>

        <FormField :label="t('settings.server.password.lengthRegular')">
          <template #default="{ fieldId }">
            <Select
              :id="fieldId"
              v-model="values.passwordLengthRegularUsers"
              :disabled="isSubmitting"
            >
              <option v-for="length in PASSWORD_REGULAR_LENGTHS" :key="length" :value="length">
                {{ length }}
              </option>
            </Select>
          </template>
        </FormField>

        <FormField :label="t('settings.server.password.lengthAdmin')">
          <template #default="{ fieldId }">
            <Select
              :id="fieldId"
              v-model="values.passwordLengthAdminUsers"
              :disabled="isSubmitting"
            >
              <option v-for="length in PASSWORD_ADMIN_LENGTHS" :key="length" :value="length">
                {{ length }}
              </option>
            </Select>
          </template>
        </FormField>
      </div>
    </Card>

    <!-- Registration -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.signup.title') }}</h2>
      <Switch v-model="values.signupEnabled" :disabled="isSubmitting">
        {{ t('settings.server.signup.enabled') }}
      </Switch>
      <Switch v-model="values.signupRequireAdminApproval" :disabled="isSubmitting">
        {{ t('settings.server.signup.adminApproval') }}
      </Switch>
      <Switch v-model="values.signupRequireEmailVerification" :disabled="isSubmitting">
        {{ t('settings.server.signup.emailVerification') }}
      </Switch>
    </Card>

    <!-- Authentication -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.sso.title') }}</h2>
      <Switch v-model="values.ssoEnabled" :disabled="isSubmitting">
        {{ t('settings.server.sso.enabled') }}
      </Switch>
      <Alert kind="info">{{ t('settings.server.sso.enabledInfo') }}</Alert>
      <Switch v-model="values.localLoginEnabled" :disabled="isSubmitting">
        {{ t('settings.server.sso.localLogin') }}
      </Switch>
      <Alert v-if="!values.localLoginEnabled" kind="warning">
        {{ t('settings.server.sso.localLoginWarning') }}
      </Alert>
      <Switch v-model="values.ssoAutoRedirect" :disabled="isSubmitting">
        {{ t('settings.server.sso.autoRedirect') }}
      </Switch>
      <Alert kind="info">{{ t('settings.server.sso.autoRedirectInfo') }}</Alert>
    </Card>

    <!-- Public sharing -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.sharing.title') }}</h2>
      <Switch v-model="values.publicShareableLinks" :disabled="isSubmitting">
        {{ t('settings.server.sharing.enabled') }}
      </Switch>
      <Alert v-if="values.publicShareableLinks" kind="warning">
        {{ t('settings.server.sharing.enabledWarning') }}
      </Alert>
      <Switch
        v-model="values.publicShareableLinksUserInfo"
        :disabled="isSubmitting || !values.publicShareableLinks"
      >
        {{ t('settings.server.sharing.userInfo') }}
      </Switch>
      <Alert
        v-if="values.publicShareableLinks && values.publicShareableLinksUserInfo"
        kind="warning"
      >
        {{ t('settings.server.sharing.userInfoWarning') }}
      </Alert>
    </Card>

    <!-- Maps -->
    <Card class="flex flex-col gap-3">
      <h2 class="text-card-heading">{{ t('settings.server.maps.title') }}</h2>

      <FormField :label="t('settings.server.maps.template')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="selectedTemplate" :disabled="isSubmitting">
            <option
              v-for="template in templates"
              :key="template.templateId"
              :value="template.templateId"
            >
              {{ template.name }}
            </option>
            <option :value="CUSTOM_TEMPLATE">{{ t('settings.server.maps.templateCustom') }}</option>
          </Select>
        </template>
      </FormField>

      <Alert v-if="!isCustomTemplate && selectedTemplateData?.requiresApiKeyBackend" kind="warning">
        {{ t('settings.server.maps.apiKeyBackendWarning') }}
      </Alert>
      <Alert v-if="!isCustomTemplate && selectedTemplateData?.requiresApiKeyFrontend" kind="info">
        {{ t('settings.server.maps.apiKeyFrontendWarning') }}
      </Alert>

      <FormField
        :label="t('settings.server.maps.url')"
        :hint="t('settings.server.maps.urlHint')"
        :error="errors.tileserverUrl"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.tileserverUrl"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="text"
            inputmode="url"
            maxlength="2048"
            :disabled="isSubmitting || !isCustomTemplate"
            @blur="handleBlur('tileserverUrl')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.server.maps.attribution')">
        <template #default="{ fieldId }">
          <Input
            :id="fieldId"
            v-model="values.tileserverAttribution"
            type="text"
            maxlength="1024"
            :disabled="isSubmitting || !isCustomTemplate"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.server.maps.apiKey')">
        <template #default="{ fieldId }">
          <Input
            :id="fieldId"
            v-model="values.tileserverApiKey"
            type="password"
            maxlength="256"
            autocomplete="off"
            :placeholder="
              settings.tileserverApiKeySet ? t('settings.server.maps.apiKeyStored') : ''
            "
            :disabled="isSubmitting || values.removeTileserverApiKey"
          />
        </template>
      </FormField>
      <Switch
        v-if="settings.tileserverApiKeySet"
        v-model="values.removeTileserverApiKey"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.maps.apiKeyRemove') }}
      </Switch>
      <Alert kind="warning">{{ t('settings.server.maps.apiKeyWarning') }}</Alert>

      <div class="flex flex-col gap-1">
        <Label for="server-map-bg-color">{{ t('settings.server.maps.backgroundColor') }}</Label>
        <div class="flex items-center gap-3">
          <input
            id="server-map-bg-color"
            v-model="values.mapBackgroundColor"
            type="color"
            class="h-9 w-16 cursor-pointer rounded-input border border-input bg-background p-1 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="isSubmitting || !isCustomTemplate"
          />
          <span class="text-body tabular-nums">{{ values.mapBackgroundColor }}</span>
        </div>
      </div>

      <Switch v-model="values.tileserverRegenerateThumbnailsOnChange" :disabled="isSubmitting">
        {{ t('settings.server.maps.regenerateThumbnails') }}
      </Switch>
    </Card>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="!isValid || isSubmitting">
        <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
        {{ isSubmitting ? t('settings.server.saving') : t('settings.server.save') }}
      </Button>
    </div>
  </form>
</template>
