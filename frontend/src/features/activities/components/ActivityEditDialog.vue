<script setup lang="ts">
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  Activity,
  ActivityEditInput,
  ActivitySummary,
  ActivityVisibility,
} from '@/features/activities/types'

import { Button } from '@/components/ui/button'
import { ErrorState } from '@/components/ui/error-state'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { inputFieldClass } from '@/components/ui/input'
import { LoadingState } from '@/components/ui/loading-state'
import { MarkdownEditor } from '@/components/ui/markdown-editor'
import { Switch } from '@/components/ui/switch'
import { isStaleWrite } from '@/services/ifMatch'
import { useToasts } from '@/composables/useToasts'
import { required } from '@/utils/validators'
import {
  useEditActivityMutation,
  useFullActivityReader,
} from '@/features/activities/composables/useActivityDetail'
import {
  ACTIVITY_TYPE_LABEL_KEYS,
  isActivityType,
  presentActivityType,
  sortActivityTypesByLabel,
} from '@/features/activities/utils/activityType'

const props = defineProps<{
  /**
   * The activity being edited. A list row has no private notes, so the dialog reads the full
   * activity when it opens; a full activity (from the detail page) seeds the form as it is.
   */
  activity: ActivitySummary | Activity
}>()

const open = defineModel<boolean>('open', { required: true })

const { t, locale } = useI18n()
const toasts = useToasts()

const editMutation = useEditActivityMutation()
const isSaving = computed(() => editMutation.isPending.value)

/** Whether the activity is the full read, which carries the private notes. */
function isFullActivity(activity: ActivitySummary | Activity): activity is Activity {
  return 'privateNotes' in activity
}

/** Projects an activity onto the editable form values; a summary has no private notes. */
function toFormValues(activity: ActivitySummary | Activity): ActivityEditInput {
  return {
    name: activity.name,
    activityType: activity.activityType,
    description: activity.description ?? '',
    privateNotes: isFullActivity(activity) ? (activity.privateNotes ?? '') : '',
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

const readFullActivity = useFullActivityReader()
/** The full activity read for a list row, once it arrives. */
const fetched = shallowRef<Activity | null>(null)
const loadFailed = ref(false)
/** Counts openings and retries so a read that finishes after the dialog moved on is dropped. */
let loadToken = 0

/** The full activity the form edits and whose version goes out as `If-Match`, or `null` while loading. */
const source = computed(() => (isFullActivity(props.activity) ? props.activity : fetched.value))
const isLoading = computed(() => source.value === null)

/**
 * Fills the form from the full activity: the one the dialog was given, or the one it reads for a
 * list row. Runs each time the dialog opens, so reopening after a cache update (or cancel) starts
 * from the server-authoritative values.
 */
async function loadAndSeed(): Promise<void> {
  const token = ++loadToken
  fetched.value = null
  loadFailed.value = false
  nameTouched.value = false
  if (isFullActivity(props.activity)) {
    Object.assign(form, toFormValues(props.activity))
    return
  }
  try {
    const full = await readFullActivity(props.activity.id)
    if (token !== loadToken) {
      return
    }
    if (full === null) {
      loadFailed.value = true
      return
    }
    fetched.value = full
    Object.assign(form, toFormValues(full))
  } catch {
    if (token === loadToken) {
      loadFailed.value = true
    }
  }
}

watch(open, (isOpen) => {
  if (isOpen) {
    void loadAndSeed()
  } else {
    loadToken += 1
  }
})

/** Activity-type options, sorted by label, for the type selector. */
const activityTypeOptions = computed(() =>
  sortActivityTypesByLabel(
    Object.keys(ACTIVITY_TYPE_LABEL_KEYS).filter(isActivityType),
    t,
    locale.value,
  ).map((value) => ({ value, labelKey: presentActivityType(value).labelKey })),
)

const visibilityOptions: { value: ActivityVisibility; labelKey: string }[] = [
  { value: 'public', labelKey: 'activities.visibility.public' },
  { value: 'followers', labelKey: 'activities.visibility.followers' },
  { value: 'private', labelKey: 'activities.visibility.private' },
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

const validateName = required<string>(t('activities.edit.nameRequired'))
const nameTouched = ref(false)
const nameError = computed(() =>
  nameTouched.value ? (validateName(form.name) ?? undefined) : undefined,
)
const canSubmit = computed(() => !isLoading.value && validateName(form.name) === null)

/** Persists the edited fields, then closes the dialog. */
async function submit(): Promise<void> {
  nameTouched.value = true
  const current = source.value
  if (!canSubmit.value || current === null) {
    return
  }
  try {
    await editMutation.mutateAsync({
      id: current.id,
      input: { ...form },
      version: current.version,
    })
    open.value = false
    toasts.success(t('activities.edit.success'))
  } catch (error) {
    // 412 is not a failure to save, it is a refusal to overwrite: the form was
    // built from a copy that someone else has since changed. Saying so lets the
    // user reopen the (now refreshed) activity instead of retrying blindly.
    if (isStaleWrite(error)) {
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
    <ErrorState v-if="isLoading && loadFailed" class="py-4" :title="t('activities.edit.loadError')">
      <template #action>
        <Button type="button" variant="outline" size="sm" @click="loadAndSeed()">
          {{ t('app.error.retry') }}
        </Button>
      </template>
    </ErrorState>
    <LoadingState v-else-if="isLoading" class="py-4" :label="t('activities.edit.loading')" />
    <div v-else class="flex flex-col gap-3">
      <FormField :label="t('activities.edit.name')" :error="nameError" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="form.name"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            class="w-full"
            :maxlength="45"
            :disabled="isSaving"
            @blur="nameTouched = true"
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
