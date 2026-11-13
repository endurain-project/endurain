<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Alert } from '@/components/ui/alert'
import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import EnvManagedHint from '@/features/serverSettings/components/EnvManagedHint.vue'
import EnvManagedNotice from '@/features/serverSettings/components/EnvManagedNotice.vue'
import {
  CUSTOM_TEMPLATE,
  useServerSettingsFormContext,
} from '@/features/serverSettings/composables/useServerSettingsForm'

const { t } = useI18n()
const {
  values,
  errors,
  isSubmitting,
  handleSubmit,
  handleBlur,
  settings,
  templates,
  envVar,
  envHint,
  envNames,
  isGeocodeService,
  geocodingHostPlaceholder,
  selectedTemplate,
  selectedTemplateData,
  isCustomTemplate,
  selectTemplate,
} = useServerSettingsFormContext()

/** The geocoding fields an environment variable can lock. */
const GEOCODING_ENV_FIELDS = [
  'geocoding_service',
  'geocoding_host',
  'geocoding_use_https',
  'geocoding_rate_limit',
  'geocoding_api_key',
]
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <Card class="flex flex-col gap-3" data-setting="section-maps">
      <h2 class="text-card-heading">{{ t('settings.server.maps.title') }}</h2>

      <FormField data-setting="maps-template" :label="t('settings.server.maps.template')">
        <template #default="{ fieldId }">
          <Select
            :id="fieldId"
            :model-value="selectedTemplate"
            :disabled="isSubmitting"
            @update:model-value="selectTemplate"
          >
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
        data-setting="maps-url"
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

      <FormField data-setting="maps-attribution" :label="t('settings.server.maps.attribution')">
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

      <FormField data-setting="maps-api-key" :label="t('settings.server.maps.apiKey')">
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

      <div class="flex flex-col gap-1" data-setting="maps-background-color">
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

      <Switch
        v-model="values.tileserverRegenerateThumbnailsOnChange"
        data-setting="maps-regenerate-thumbnails"
        :disabled="isSubmitting"
      >
        {{ t('settings.server.maps.regenerateThumbnails') }}
      </Switch>
    </Card>

    <Card class="flex flex-col gap-3" data-setting="section-geocoding">
      <div class="flex flex-col gap-1">
        <h2 class="text-card-heading">{{ t('settings.server.geocoding.title') }}</h2>
        <p class="text-body">{{ t('settings.server.geocoding.description') }}</p>
      </div>
      <EnvManagedNotice :names="envNames(GEOCODING_ENV_FIELDS)" />

      <FormField
        data-setting="geocoding-service"
        :label="t('settings.server.geocoding.service')"
        :hint="envHint('geocoding_service')"
      >
        <template #default="{ fieldId, describedBy }">
          <Select
            :id="fieldId"
            v-model="values.geocodingService"
            :aria-describedby="describedBy"
            :disabled="isSubmitting || Boolean(envVar('geocoding_service'))"
          >
            <option value="nominatim">{{ t('settings.server.geocoding.serviceNominatim') }}</option>
            <option value="photon">{{ t('settings.server.geocoding.servicePhoton') }}</option>
            <option value="geocode">{{ t('settings.server.geocoding.serviceGeocode') }}</option>
          </Select>
        </template>
      </FormField>

      <template v-if="!isGeocodeService">
        <FormField
          data-setting="geocoding-host"
          :label="t('settings.server.geocoding.host')"
          :hint="envHint('geocoding_host') ?? t('settings.server.geocoding.hostHint')"
        >
          <template #default="{ fieldId, describedBy }">
            <Input
              :id="fieldId"
              v-model="values.geocodingHost"
              :aria-describedby="describedBy"
              type="text"
              maxlength="253"
              autocomplete="off"
              :placeholder="geocodingHostPlaceholder"
              :disabled="isSubmitting || Boolean(envVar('geocoding_host'))"
            />
          </template>
        </FormField>

        <Switch
          v-model="values.geocodingUseHttps"
          data-setting="geocoding-use-https"
          :disabled="isSubmitting || Boolean(envVar('geocoding_use_https'))"
        >
          {{ t('settings.server.geocoding.useHttps') }}
        </Switch>
        <EnvManagedHint :name="envVar('geocoding_use_https')" />
      </template>

      <FormField
        data-setting="geocoding-rate-limit"
        :label="t('settings.server.geocoding.rateLimit')"
        :hint="envHint('geocoding_rate_limit') ?? t('settings.server.geocoding.rateLimitHint')"
        :error="errors.geocodingRateLimit"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.geocodingRateLimit"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="text"
            inputmode="decimal"
            maxlength="6"
            :disabled="isSubmitting || Boolean(envVar('geocoding_rate_limit'))"
            @blur="handleBlur('geocodingRateLimit')"
          />
        </template>
      </FormField>

      <template v-if="isGeocodeService">
        <FormField
          data-setting="geocoding-api-key"
          :label="t('settings.server.geocoding.apiKey')"
          :hint="envHint('geocoding_api_key')"
        >
          <template #default="{ fieldId, describedBy }">
            <Input
              :id="fieldId"
              v-model="values.geocodingApiKey"
              :aria-describedby="describedBy"
              type="password"
              maxlength="256"
              autocomplete="off"
              :placeholder="
                settings.geocodingApiKeySet ? t('settings.server.geocoding.apiKeyStored') : ''
              "
              :disabled="
                isSubmitting || values.removeGeocodingApiKey || Boolean(envVar('geocoding_api_key'))
              "
            />
          </template>
        </FormField>
        <Switch
          v-if="settings.geocodingApiKeySet"
          v-model="values.removeGeocodingApiKey"
          :disabled="isSubmitting || Boolean(envVar('geocoding_api_key'))"
        >
          {{ t('settings.server.geocoding.apiKeyRemove') }}
        </Switch>
      </template>
    </Card>
  </form>
</template>
