<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  FastingEntry,
  FastingEntryInput,
  FastingStatus,
  FastingType,
} from '@/features/health/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import {
  dateTimeLocalToIso,
  nowDateTimeLocalInput,
  toDateTimeLocalInput,
} from '@/features/health/utils/healthFormat'
import { toNumberOrNull } from '@/utils/number'
import { required } from '@/utils/validators'
import {
  useCreateFastingEntryMutation,
  useUpdateFastingEntryMutation,
} from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The fasting session being edited, or `null`/absent when starting a new one. */
    entry?: FastingEntry | null
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateFastingEntryMutation()
const updateMutation = useUpdateFastingEntryMutation()

/** The fasting protocols offered in the select, in display order. */
const FASTING_TYPES: FastingType[] = [
  '16:8',
  '18:6',
  '20:4',
  'OMAD',
  '24h',
  '36h',
  '48h',
  '72h',
  'custom',
]

/** The statuses offered when editing, in display order. */
const FASTING_STATUSES: FastingStatus[] = ['in_progress', 'completed', 'broken', 'cancelled']

/** Target duration (seconds) implied by each non-custom protocol. */
const FASTING_DURATIONS: Partial<Record<FastingType, number>> = {
  '16:8': 16 * 3600,
  '18:6': 18 * 3600,
  '20:4': 20 * 3600,
  OMAD: 23 * 3600,
  '24h': 24 * 3600,
  '36h': 36 * 3600,
  '48h': 48 * 3600,
  '72h': 72 * 3600,
}

/** Maximum length of the free-text notes field. */
const NOTES_MAX_LENGTH = 500

/** Form shape: every field is kept as a string and parsed at submit. */
interface FastingFormValues {
  type: string
  customHours: string
  startTime: string
  endTime: string
  status: string
  notes: string
}

/** The pristine values used for "start" and as the reset baseline. */
function defaultValues(): FastingFormValues {
  return {
    type: '16:8',
    customHours: '',
    startTime: nowDateTimeLocalInput(),
    endTime: '',
    status: 'in_progress',
    notes: '',
  }
}

const isEditing = computed(() => props.entry !== null)

/**
 * Target duration in seconds: the protocol's fixed length, or the parsed custom
 * hours. `null` when a custom duration is required but missing/invalid, which
 * disables submit.
 */
const targetSeconds = computed<number | null>(() => {
  if (values.type === 'custom') {
    const hours = toNumberOrNull(values.customHours)
    if (hours === null || hours <= 0) {
      return null
    }
    return Math.round(hours * 3600)
  }
  return FASTING_DURATIONS[values.type as FastingType] ?? null
})

/** Converts the string-based form values into the clean {@link FastingEntryInput}. */
function buildInput(formValues: FastingFormValues): FastingEntryInput {
  const start = dateTimeLocalToIso(formValues.startTime)
  const end = isEditing.value ? dateTimeLocalToIso(formValues.endTime) : null
  const notes = formValues.notes.trim()

  // When editing a finished fast, derive the actual length from the bounds.
  let actualDurationSeconds: number | null = null
  if (start && end) {
    const diff = Math.floor((new Date(end).getTime() - new Date(start).getTime()) / 1000)
    actualDurationSeconds = diff > 0 ? diff : null
  }

  return {
    fastStartTime: start,
    fastEndTime: end,
    fastingType: (formValues.type as FastingType) || null,
    targetDurationSeconds: targetSeconds.value,
    actualDurationSeconds,
    status: isEditing.value ? (formValues.status as FastingStatus) || null : null,
    notes: notes ? notes : null,
  }
}

/**
 * Persists the fast, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param formValues - The validated form values.
 */
async function submitForm(formValues: FastingFormValues): Promise<void> {
  const input = buildInput(formValues)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        userId: props.entry.userId,
        input,
      })
      emit('success', t('health.fasting.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.fasting.form.createSuccess'))
    }
    open.value = false
  } catch {
    emit('error', t('health.fasting.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<FastingFormValues>({
    initialValues: defaultValues(),
    validators: {
      startTime: required<string>(t('health.fasting.form.startTimeRequired')),
    },
    onSubmit: submitForm,
  })

// A custom protocol needs a valid hours value before the fast can be saved.
const canSubmit = computed(() => isValid.value && targetSeconds.value !== null)

const dialogTitle = computed(() =>
  isEditing.value ? t('health.fasting.form.editTitle') : t('health.fasting.form.addTitle'),
)

/** Seeds the form from the entry being edited, or pristine defaults for "start". */
function populate(): void {
  reset()
  const entry = props.entry
  if (!entry) {
    values.startTime = nowDateTimeLocalInput()
    return
  }
  const type = entry.fastingType ?? '16:8'
  values.type = type
  if (type === 'custom' && entry.targetDurationSeconds) {
    values.customHours = String(Math.round((entry.targetDurationSeconds / 3600) * 100) / 100)
  }
  values.startTime = entry.fastStartTime
    ? toDateTimeLocalInput(entry.fastStartTime)
    : nowDateTimeLocalInput()
  values.endTime = entry.fastEndTime ? toDateTimeLocalInput(entry.fastEndTime) : ''
  values.status = entry.status ?? 'in_progress'
  values.notes = entry.notes ?? ''
}

// Re-seed each time the dialog opens; the parent sets `entry` before opening.
watch(open, (isOpen) => {
  if (isOpen) {
    populate()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="dialogTitle"
    :description="t('health.fasting.form.description')"
    :submit-label="isEditing ? t('health.fasting.form.save') : t('health.fasting.form.create')"
    :cancel-label="t('health.fasting.form.cancel')"
    :close-label="t('health.fasting.form.close')"
    :submitting="isSubmitting"
    :can-submit="canSubmit"
    @submit="handleSubmit"
  >
    <div class="flex flex-col gap-2">
      <FormField :label="t('health.fasting.form.type')">
        <template #default="{ fieldId }">
          <select
            :id="fieldId"
            v-model="values.type"
            :class="inputFieldClass"
            :disabled="isSubmitting"
          >
            <option v-for="type in FASTING_TYPES" :key="type" :value="type">
              {{ t(`health.fasting.types.${type}`) }}
            </option>
          </select>
        </template>
      </FormField>

      <FormField
        v-if="values.type === 'custom'"
        :label="t('health.fasting.form.customDuration')"
        :hint="t('health.fasting.form.customDurationHint')"
      >
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.customHours"
            :class="inputFieldClass"
            type="number"
            min="1"
            max="72"
            step="0.5"
            inputmode="decimal"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField :label="t('health.fasting.form.startTime')" :error="errors.startTime" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.startTime"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="datetime-local"
            :disabled="isSubmitting"
            @blur="handleBlur('startTime')"
          />
        </template>
      </FormField>

      <template v-if="isEditing">
        <FormField :label="t('health.fasting.form.endTime')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.endTime"
              :class="inputFieldClass"
              type="datetime-local"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.fasting.form.status')">
          <template #default="{ fieldId }">
            <select
              :id="fieldId"
              v-model="values.status"
              :class="inputFieldClass"
              :disabled="isSubmitting"
            >
              <option v-for="status in FASTING_STATUSES" :key="status" :value="status">
                {{ t(`health.fasting.status.${status}`) }}
              </option>
            </select>
          </template>
        </FormField>
      </template>

      <FormField :label="t('health.fasting.form.notes')">
        <template #default="{ fieldId }">
          <textarea
            :id="fieldId"
            v-model="values.notes"
            :class="inputFieldClass"
            :maxlength="NOTES_MAX_LENGTH"
            rows="3"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>
    </div>
  </FormDialog>
</template>
