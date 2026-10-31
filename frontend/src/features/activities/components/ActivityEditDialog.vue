<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity, ActivityEditInput } from '@/features/activities/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input'
import { MarkdownEditor } from '@/components/ui/markdown-editor'
import { Switch } from '@/components/ui/switch'
import { HttpError } from '@/services/http'
import { useToasts } from '@/composables/useToasts'
import { useEditActivityMutation } from '@/features/activities/composables/useActivityDetail'
import { ACTIVITY_TYPE_LABEL_KEYS } from '@/features/activities/utils/activityType'

const props = defineProps<{
  /** The activity being edited; seeds the form whenever the dialog opens. */
  activity: Activity
}>()

const open = defineModel<boolean>('open', { required: true })

const { t } = useI18n()
const toasts = useToasts()

const editMutation = useEditActivityMutation()
const isSaving = computed(() => editMutation.isPending.value)

/** Projects an activity onto the editable form values. */
function toFormValues(activity: Activity): ActivityEditInput {
  return {
    name: activity.name,
    activityType: activity.activityType,
    description: activity.description ?? '',
    privateNotes: activity.privateNotes ?? '',
    visibility: activity.visibility,
    isHidden: activity.isHidden,
    hideStartTime: activity.privacy.hideStartTime,
    hideLocation: activity.privacy.hideLocation,
    hideMap: activity.privacy.hideMap,
    hideHr: activity.privacy.hideHr,
    hidePower: activity.privacy.hidePower,
    hideCadence: activity.privacy.hideCadence,
    hideElevation: activity.privacy.hideElevation,
    hideSpeed: activity.privacy.hideSpeed,
    hidePace: activity.privacy.hidePace,
    hideLaps: activity.privacy.hideLaps,
    hideWorkoutSetsSteps: activity.privacy.hideWorkoutSetsSteps,
    hideGear: activity.privacy.hideGear,
  }
}

const form = reactive<ActivityEditInput>(toFormValues(props.activity))

// Re-seed the form from the activity each time the dialog opens, so reopening
// after a cache update (or cancel) starts from the server-authoritative values.
watch(open, (isOpen) => {
  if (isOpen) {
    Object.assign(form, toFormValues(props.activity))
  }
})

/** Activity-type options, sorted by code, for the type selector. */
const activityTypeOptions = computed(() =>
  Object.entries(ACTIVITY_TYPE_LABEL_KEYS)
    .map(([value, labelKey]) => ({ value: Number(value), labelKey }))
    .sort((a, b) => a.value - b.value),
)

const visibilityOptions = [
  { value: 0, labelKey: 'activities.visibility.public' },
  { value: 1, labelKey: 'activities.visibility.followers' },
  { value: 2, labelKey: 'activities.visibility.private' },
]

/** The per-metric "hide from others" toggles, mirroring v1's edit modal. */
const privacyFields = [
  { key: 'hideStartTime', labelKey: 'activities.edit.hideStartTime' },
  { key: 'hideLocation', labelKey: 'activities.edit.hideLocation' },
  { key: 'hideMap', labelKey: 'activities.edit.hideMap' },
  { key: 'hideHr', labelKey: 'activities.edit.hideHr' },
  { key: 'hidePower', labelKey: 'activities.edit.hidePower' },
  { key: 'hideCadence', labelKey: 'activities.edit.hideCadence' },
  { key: 'hideElevation', labelKey: 'activities.edit.hideElevation' },
  { key: 'hideSpeed', labelKey: 'activities.edit.hideSpeed' },
  { key: 'hidePace', labelKey: 'activities.edit.hidePace' },
  { key: 'hideLaps', labelKey: 'activities.edit.hideLaps' },
  { key: 'hideWorkoutSetsSteps', labelKey: 'activities.edit.hideWorkoutSetsSteps' },
  { key: 'hideGear', labelKey: 'activities.edit.hideGear' },
] as const

const canSubmit = computed(() => form.name.trim().length > 0)

/** Persists the edited fields, then closes the dialog. */
async function submit(): Promise<void> {
  if (!canSubmit.value) {
    return
  }
  try {
    await editMutation.mutateAsync({
      id: props.activity.id,
      input: { ...form },
      version: props.activity.version,
    })
    open.value = false
    toasts.success(t('activities.edit.success'))
  } catch (error) {
    // 412 is not a failure to save, it is a refusal to overwrite: the form was
    // built from a copy that someone else has since changed. Saying so lets the
    // user reopen the (now refreshed) activity instead of retrying blindly.
    if (error instanceof HttpError && error.status === 412) {
      open.value = false
      toasts.error(t('activities.edit.staleError'))
      return
    }
    toasts.error(t('activities.edit.error'))
  }
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('activities.edit.title')"
    :submit-label="t('activities.edit.save')"
    :cancel-label="t('activities.edit.cancel')"
    :close-label="t('activities.edit.close')"
    :submitting="isSaving"
    :can-submit="canSubmit"
    content-class="sm:max-w-2xl"
    @submit="submit"
  >
    <div class="flex flex-col gap-3">
      <FormField :label="t('activities.edit.name')">
        <template #default="{ fieldId }">
          <Input
            :id="fieldId"
            v-model="form.name"
            class="w-full"
            :maxlength="45"
            :disabled="isSaving"
          />
        </template>
      </FormField>

      <FormField :label="t('activities.edit.type')">
        <template #default="{ fieldId }">
          <select
            :id="fieldId"
            v-model="form.activityType"
            :class="[inputFieldClass, 'w-full']"
            :disabled="isSaving"
          >
            <option v-for="opt in activityTypeOptions" :key="opt.value" :value="opt.value">
              {{ t(opt.labelKey) }}
            </option>
          </select>
        </template>
      </FormField>

      <FormField :label="t('activities.edit.description')">
        <template #default="{ fieldId }">
          <MarkdownEditor
            :id="fieldId"
            v-model="form.description"
            :rows="3"
            :maxlength="2500"
            :disabled="isSaving"
          />
        </template>
      </FormField>

      <FormField :label="t('activities.edit.privateNotes')">
        <template #default="{ fieldId }">
          <MarkdownEditor
            :id="fieldId"
            v-model="form.privateNotes"
            :rows="3"
            :maxlength="2500"
            :disabled="isSaving"
          />
        </template>
      </FormField>

      <FormField :label="t('activities.edit.visibility')">
        <template #default="{ fieldId }">
          <select
            :id="fieldId"
            v-model="form.visibility"
            :class="[inputFieldClass, 'w-full']"
            :disabled="isSaving"
          >
            <option v-for="opt in visibilityOptions" :key="opt.value" :value="opt.value">
              {{ t(opt.labelKey) }}
            </option>
          </select>
        </template>
      </FormField>

      <Switch v-model="form.isHidden" :disabled="isSaving">{{
        t('activities.edit.isHidden')
      }}</Switch>

      <div class="flex flex-col gap-2 border-t border-border pt-4">
        <p class="text-caption">{{ t('activities.edit.privacyTitle') }}</p>
        <div class="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
          <Switch
            v-for="field in privacyFields"
            :key="field.key"
            v-model="form[field.key]"
            :disabled="isSaving"
          >
            {{ t(field.labelKey) }}
          </Switch>
        </div>
      </div>
    </div>
  </FormDialog>
</template>
