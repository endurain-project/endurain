<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Card } from '@/components/ui/card'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import EnvManagedNotice from '@/features/serverSettings/components/EnvManagedNotice.vue'
import LoginPhotoCard from '@/features/serverSettings/components/LoginPhotoCard.vue'
import { useServerSettingsFormContext } from '@/features/serverSettings/composables/useServerSettingsForm'

const { t } = useI18n()
const {
  values,
  errors,
  isSubmitting,
  handleSubmit,
  handleBlur,
  settings,
  envVar,
  envHint,
  envNames,
} = useServerSettingsFormContext()

/** Records-per-page options offered in the list (mirrors v1). */
const NUM_RECORDS_OPTIONS = [5, 10, 25, 50, 100] as const
</script>

<template>
  <form class="flex flex-col gap-3" novalidate @submit.prevent="handleSubmit">
    <Card class="flex flex-col gap-3" data-setting="section-general">
      <h2 class="text-card-heading">{{ t('settings.server.general.title') }}</h2>
      <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <FormField data-setting="general-units" :label="t('settings.server.general.units')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.units" :disabled="isSubmitting">
              <option value="metric">{{ t('settings.server.general.unitsMetric') }}</option>
              <option value="imperial">{{ t('settings.server.general.unitsImperial') }}</option>
            </Select>
          </template>
        </FormField>

        <FormField data-setting="general-currency" :label="t('settings.server.general.currency')">
          <template #default="{ fieldId }">
            <Select :id="fieldId" v-model="values.currency" :disabled="isSubmitting">
              <option value="euro">{{ t('settings.server.general.currencyEuro') }}</option>
              <option value="dollar">{{ t('settings.server.general.currencyDollar') }}</option>
              <option value="pound">{{ t('settings.server.general.currencyPound') }}</option>
            </Select>
          </template>
        </FormField>

        <FormField
          data-setting="general-num-records"
          :label="t('settings.server.general.numRecords')"
        >
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

    <Card class="flex flex-col gap-3" data-setting="section-retention">
      <h2 class="text-card-heading">{{ t('settings.server.retention.title') }}</h2>
      <EnvManagedNotice :names="envNames(['read_notification_retention_days'])" />
      <FormField
        data-setting="retention-read-notifications"
        :label="t('settings.server.retention.readNotifications')"
        :hint="
          envHint('read_notification_retention_days') ??
          t('settings.server.retention.readNotificationsHint')
        "
        :error="errors.readNotificationRetentionDays"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.readNotificationRetentionDays"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="text"
            inputmode="numeric"
            maxlength="4"
            :disabled="isSubmitting || Boolean(envVar('read_notification_retention_days'))"
            @blur="handleBlur('readNotificationRetentionDays')"
          />
        </template>
      </FormField>
    </Card>

    <LoginPhotoCard data-setting="section-photo" :login-photo-set="settings.loginPhotoSet" />
  </form>
</template>
