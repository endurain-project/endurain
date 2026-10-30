<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoaderCircle, ShieldCheck } from '@lucide/vue'

import type { ActivityVisibility, PrivacySettings } from '@/features/profile/types'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { FormField } from '@/components/ui/form-field'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { useToasts } from '@/composables/useToasts'
import {
  useUpdateExistingActivitiesVisibilityMutation,
  useUpdatePrivacyMutation,
} from '@/features/profile/composables/useProfile'

const props = defineProps<{
  /** The loaded privacy settings; seeds the form (mounted only after load). */
  privacy: PrivacySettings
}>()

const { t } = useI18n()
const toasts = useToasts()
const updateMutation = useUpdatePrivacyMutation()
const bulkVisibilityMutation = useUpdateExistingActivitiesVisibilityMutation()
const isBulkConfirmOpen = ref(false)
const bulkVisibility = ref<ActivityVisibility>(props.privacy.defaultActivityVisibility)

const VISIBILITY_OPTIONS: { value: ActivityVisibility; labelKey: string }[] = [
  { value: 'public', labelKey: 'settings.profile.privacy.visibilityPublic' },
  { value: 'followers', labelKey: 'settings.profile.privacy.visibilityFollowers' },
  { value: 'private', labelKey: 'settings.profile.privacy.visibilityPrivate' },
]

/** The per-field hide toggles, in display order. */
type HideKey = Exclude<keyof PrivacySettings, 'defaultActivityVisibility' | 'version'>
const HIDE_FIELDS: { key: HideKey; labelKey: string }[] = [
  { key: 'hideStartTime', labelKey: 'settings.profile.privacy.hideStartTime' },
  { key: 'hideLocation', labelKey: 'settings.profile.privacy.hideLocation' },
  { key: 'hideMap', labelKey: 'settings.profile.privacy.hideMap' },
  { key: 'hideHr', labelKey: 'settings.profile.privacy.hideHr' },
  { key: 'hidePower', labelKey: 'settings.profile.privacy.hidePower' },
  { key: 'hideCadence', labelKey: 'settings.profile.privacy.hideCadence' },
  { key: 'hideElevation', labelKey: 'settings.profile.privacy.hideElevation' },
  { key: 'hideSpeed', labelKey: 'settings.profile.privacy.hideSpeed' },
  { key: 'hidePace', labelKey: 'settings.profile.privacy.hidePace' },
  { key: 'hideLaps', labelKey: 'settings.profile.privacy.hideLaps' },
  { key: 'hideWorkoutSetsSteps', labelKey: 'settings.profile.privacy.hideWorkoutSetsSteps' },
  { key: 'hideGear', labelKey: 'settings.profile.privacy.hideGear' },
]

/**
 * Persists the privacy settings, surfacing the outcome as a toast.
 *
 * @param values - The current privacy settings.
 */
async function submitPrivacy(values: PrivacySettings): Promise<void> {
  try {
    await updateMutation.mutateAsync(values)
    toasts.success(t('settings.profile.privacy.saveSuccess'))
  } catch (error) {
    toasts.error(
      isStaleWrite(error) ? t('app.staleError') : t('settings.profile.privacy.saveError'),
    )
  }
}

/**
 * Applies the selected visibility to every existing activity after confirmation.
 */
async function submitExistingActivitiesVisibility(): Promise<void> {
  try {
    await bulkVisibilityMutation.mutateAsync(bulkVisibility.value)
    isBulkConfirmOpen.value = false
    toasts.success(t('settings.profile.privacy.bulkVisibilitySuccess'))
  } catch {
    toasts.error(t('settings.profile.privacy.bulkVisibilityError'))
  }
}

const { values, isSubmitting, handleSubmit } = useForm<PrivacySettings>({
  initialValues: { ...props.privacy },
  onSubmit: submitPrivacy,
})
</script>

<template>
  <Card class="flex flex-col gap-3" as="form" @submit.prevent="handleSubmit">
    <div class="flex flex-col gap-1">
      <h2 class="text-card-heading">{{ t('settings.profile.privacy.title') }}</h2>
      <p class="text-body">{{ t('settings.profile.privacy.subtitle') }}</p>
    </div>

    <FormField
      class="sm:max-w-xs"
      :label="t('settings.profile.privacy.defaultVisibility')"
      :hint="t('settings.profile.privacy.defaultVisibilityHint')"
    >
      <template #default="{ fieldId }">
        <Select :id="fieldId" v-model="values.defaultActivityVisibility" :disabled="isSubmitting">
          <option v-for="option in VISIBILITY_OPTIONS" :key="option.value" :value="option.value">
            {{ t(option.labelKey) }}
          </option>
        </Select>
      </template>
    </FormField>

    <div class="rounded-input border border-border bg-muted-foreground/10 p-3">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <FormField
          class="sm:max-w-xs sm:flex-1"
          :label="t('settings.profile.privacy.bulkVisibility')"
          :hint="t('settings.profile.privacy.bulkVisibilityHint')"
        >
          <template #default="{ fieldId }">
            <Select
              :id="fieldId"
              v-model="bulkVisibility"
              :disabled="bulkVisibilityMutation.isPending.value"
            >
              <option
                v-for="option in VISIBILITY_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ t(option.labelKey) }}
              </option>
            </Select>
          </template>
        </FormField>
        <Button
          type="button"
          variant="outline"
          class="w-full sm:w-auto"
          :disabled="bulkVisibilityMutation.isPending.value"
          @click="isBulkConfirmOpen = true"
        >
          <LoaderCircle
            v-if="bulkVisibilityMutation.isPending.value"
            class="size-4 animate-spin"
            aria-hidden="true"
          />
          <ShieldCheck v-else class="size-4" aria-hidden="true" />
          <span>{{ t('settings.profile.privacy.bulkVisibilityApply') }}</span>
        </Button>
      </div>
    </div>

    <div class="flex flex-col gap-1">
      <p class="text-caption">{{ t('settings.profile.privacy.hideTitle') }}</p>
      <div class="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
        <Switch
          v-for="field in HIDE_FIELDS"
          :key="field.key"
          v-model="values[field.key]"
          :disabled="isSubmitting"
        >
          {{ t(field.labelKey) }}
        </Switch>
      </div>
    </div>

    <div class="flex justify-begin">
      <Button type="submit" class="w-full sm:w-auto" :disabled="isSubmitting">
        <LoaderCircle v-if="isSubmitting" class="size-4 animate-spin" aria-hidden="true" />
        {{
          isSubmitting ? t('settings.profile.privacy.saving') : t('settings.profile.privacy.save')
        }}
      </Button>
    </div>
  </Card>

  <ConfirmDialog
    v-model:open="isBulkConfirmOpen"
    :title="t('settings.profile.privacy.bulkVisibilityConfirmTitle')"
    :description="t('settings.profile.privacy.bulkVisibilityConfirmBody')"
    :confirm-label="t('settings.profile.privacy.bulkVisibilityConfirm')"
    :cancel-label="t('settings.profile.privacy.bulkVisibilityCancel')"
    :close-label="t('settings.profile.privacy.bulkVisibilityClose')"
    :pending="bulkVisibilityMutation.isPending.value"
    confirm-variant="default"
    @confirm="submitExistingActivitiesVisibility"
  />
</template>
