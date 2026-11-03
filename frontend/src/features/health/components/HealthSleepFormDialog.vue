<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2 } from '@lucide/vue'

import type { SleepEntry, SleepEntryInput, SleepStage } from '@/features/health/types'

import { Button } from '@/components/ui/button'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { HttpError } from '@/services/http'
import { isStaleWrite } from '@/services/ifMatch'
import { todayDateTimeLocalMax } from '@/features/health/utils/healthFormat'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { compose, numberBetween, required, type Validator } from '@/utils/validators'
import {
  useCreateSleepEntryMutation,
  useUpdateSleepEntryMutation,
} from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The sleep entry being edited, or `null`/absent when logging a new one. */
    entry?: SleepEntry | null
  }>(),
  { entry: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateSleepEntryMutation()
const updateMutation = useUpdateSleepEntryMutation()

/** Form shape: every numeric field is kept as a string and parsed at submit. */
interface SleepFormValues {
  date: string
  sleepStartTimeLocal: string
  sleepEndTimeLocal: string
  totalHours: string
  totalMinutes: string
  deepHours: string
  deepMinutes: string
  lightHours: string
  lightMinutes: string
  remHours: string
  remMinutes: string
  awakeHours: string
  awakeMinutes: string
  awakeCount: string
  sleepScore: string
  restingHeartRate: string
  avgHeartRate: string
  minHeartRate: string
  maxHeartRate: string
  spo2: string
  lowestSpo2: string
  highestSpo2: string
  avgSleepStress: string
  skinTempDeviation: string
}

/** One editable sleep-stage row; numeric fields stay as strings until submit. */
interface StageRow {
  stageType: string
  startTimeGmt: string
  endTimeGmt: string
  durationHours: string
  durationMinutes: string
}

/** Combines an hours/minutes pair into total seconds, or `null` when both empty. */
function hmToSeconds(hours: string, minutes: string): number | null {
  const h = toNumberOrNull(hours)
  const m = toNumberOrNull(minutes)
  if (h === null && m === null) {
    return null
  }
  return Math.round((h ?? 0) * 3600 + (m ?? 0) * 60)
}

/** Splits a seconds value into hours/minutes form strings (blank when absent). */
function secondsToHm(seconds: number | null): { hours: string; minutes: string } {
  if (seconds === null || seconds <= 0) {
    return { hours: '', minutes: '' }
  }
  return {
    hours: String(Math.floor(seconds / 3600)),
    minutes: String(Math.round((seconds % 3600) / 60)),
  }
}

/** Trims an ISO timestamp to the `yyyy-MM-ddThh:mm` a datetime-local input wants. */
function toDateTimeLocal(value: string | null): string {
  return value ? value.slice(0, 16) : ''
}

/** Editable stage rows, managed outside the form so the array resets cleanly. */
const stages = ref<StageRow[]>([])

/** Appends a blank stage row defaulted to deep sleep. */
function addStage(): void {
  stages.value.push({
    stageType: '0',
    startTimeGmt: '',
    endTimeGmt: '',
    durationHours: '',
    durationMinutes: '',
  })
}

/** Removes the stage row at the given index. */
function removeStage(index: number): void {
  stages.value.splice(index, 1)
}

/** Maps a stage row to the clean {@link SleepStage}, or `null` when fully blank. */
function buildStage(row: StageRow): SleepStage | null {
  const startTimeGmt = row.startTimeGmt || null
  const endTimeGmt = row.endTimeGmt || null
  const durationSeconds = hmToSeconds(row.durationHours, row.durationMinutes)
  if (startTimeGmt === null && endTimeGmt === null && durationSeconds === null) {
    return null
  }
  return {
    stageType: toNumberOrNull(row.stageType),
    startTimeGmt,
    endTimeGmt,
    durationSeconds,
  }
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): SleepFormValues {
  return {
    date: todayIsoDate(),
    sleepStartTimeLocal: '',
    sleepEndTimeLocal: '',
    totalHours: '',
    totalMinutes: '',
    deepHours: '',
    deepMinutes: '',
    lightHours: '',
    lightMinutes: '',
    remHours: '',
    remMinutes: '',
    awakeHours: '',
    awakeMinutes: '',
    awakeCount: '',
    sleepScore: '',
    restingHeartRate: '',
    avgHeartRate: '',
    minHeartRate: '',
    maxHeartRate: '',
    spo2: '',
    lowestSpo2: '',
    highestSpo2: '',
    avgSleepStress: '',
    skinTempDeviation: '',
  }
}

/** Converts the string-based form values into the clean {@link SleepEntryInput}. */
function buildInput(values: SleepFormValues): SleepEntryInput {
  return {
    date: values.date || null,
    sleepStartTimeLocal: values.sleepStartTimeLocal || null,
    sleepEndTimeLocal: values.sleepEndTimeLocal || null,
    totalSleepSeconds: hmToSeconds(values.totalHours, values.totalMinutes),
    deepSleepSeconds: hmToSeconds(values.deepHours, values.deepMinutes),
    lightSleepSeconds: hmToSeconds(values.lightHours, values.lightMinutes),
    remSleepSeconds: hmToSeconds(values.remHours, values.remMinutes),
    awakeSleepSeconds: hmToSeconds(values.awakeHours, values.awakeMinutes),
    sleepScoreOverall: toNumberOrNull(values.sleepScore),
    restingHeartRate: toNumberOrNull(values.restingHeartRate),
    avgHeartRate: toNumberOrNull(values.avgHeartRate),
    minHeartRate: toNumberOrNull(values.minHeartRate),
    maxHeartRate: toNumberOrNull(values.maxHeartRate),
    avgSkinTempDeviation: toNumberOrNull(values.skinTempDeviation),
    avgSpo2: toNumberOrNull(values.spo2),
    lowestSpo2: toNumberOrNull(values.lowestSpo2),
    highestSpo2: toNumberOrNull(values.highestSpo2),
    avgSleepStress: toNumberOrNull(values.avgSleepStress),
    awakeCount: toNumberOrNull(values.awakeCount),
    sleepStages: stages.value
      .map(buildStage)
      .filter((stage): stage is SleepStage => stage !== null),
  }
}

/**
 * Persists the entry, emitting the outcome to the parent and closing on success.
 * Backend failures are mapped to a toast message rather than thrown, so the
 * dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: SleepFormValues): Promise<void> {
  if (stageErrors.value.some(Boolean)) {
    openSections.stages = true
    return
  }
  const input = buildInput(values)
  try {
    if (props.entry) {
      await updateMutation.mutateAsync({
        id: props.entry.id,
        version: props.entry.version,
        input,
      })
      emit('success', t('health.sleep.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('health.sleep.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    if (isStaleWrite(error)) {
      open.value = false
      emit('error', t('app.staleError'))
    } else if (error instanceof HttpError && error.status === 400) {
      emit('error', t('health.sleep.form.inconsistentError'))
    } else {
      emit('error', t('health.sleep.form.saveError'))
    }
  }
}

/** Largest minutes value of an hours/minutes pair. */
const MAX_MINUTES = 59

/** Shared input class: fills its grid cell and may shrink inside a flex row. */
const fieldClass = `${inputFieldClass} w-full min-w-0`

const sectionClass = 'mt-2 rounded-input border border-border px-3 py-2'

/** Mirrors a native `<details>` toggle into `openSections` so the user's choice sticks. */
function onToggle(name: SectionName, event: Event): void {
  openSections[name] = (event.target as HTMLDetailsElement).open
}

/**
 * Bounds a numeric text field with a translated message; blank values pass so optional fields stay optional.
 *
 * @param min - Smallest accepted value.
 * @param max - Largest accepted value, or `undefined` for no upper bound.
 * @returns A validator returning the range message when the value is out of bounds.
 */
function bounded(min: number, max?: number): Validator<string> {
  return numberBetween(
    min,
    max,
    max === undefined
      ? t('health.sleep.form.numberMin', { min })
      : t('health.sleep.form.numberRange', { min, max }),
  )
}

/** Seconds the stage breakdown may exceed the total by (the backend's tolerance). */
const STAGE_TOLERANCE_SECONDS = 60

/** Rejects deep, light and REM sleep that add up to more than the total (mirrors the backend rule). */
function stagesWithinTotal(): string | null {
  const total = hmToSeconds(values.totalHours, values.totalMinutes)
  if (total === null) {
    return null
  }
  const stagesTotal = [
    hmToSeconds(values.deepHours, values.deepMinutes),
    hmToSeconds(values.lightHours, values.lightMinutes),
    hmToSeconds(values.remHours, values.remMinutes),
  ].reduce<number>((sum, seconds) => sum + (seconds ?? 0), 0)
  return stagesTotal > total + STAGE_TOLERANCE_SECONDS
    ? t('health.sleep.form.stagesExceedTotal')
    : null
}

/** Number fields with backend bounds (`health_sleep/schema.py`). */
/** Inclusive numeric bounds; `max` is absent for lower-bound-only fields. */
type Bounds = readonly [min: number, max?: number]

function bounds(min: number, max?: number): Bounds {
  return [min, max]
}

const boundedFields = {
  totalMinutes: bounds(0, MAX_MINUTES),
  deepHours: bounds(0),
  deepMinutes: bounds(0, MAX_MINUTES),
  lightHours: bounds(0),
  lightMinutes: bounds(0, MAX_MINUTES),
  remHours: bounds(0),
  remMinutes: bounds(0, MAX_MINUTES),
  awakeHours: bounds(0),
  awakeMinutes: bounds(0, MAX_MINUTES),
  awakeCount: bounds(0),
  sleepScore: bounds(0, 100),
  restingHeartRate: bounds(20, 220),
  avgHeartRate: bounds(20, 220),
  minHeartRate: bounds(20, 220),
  maxHeartRate: bounds(20, 220),
  spo2: bounds(70, 100),
  lowestSpo2: bounds(70, 100),
  highestSpo2: bounds(70, 100),
  avgSleepStress: bounds(0, 100),
}

const boundedValidators = Object.fromEntries(
  (Object.entries(boundedFields) as [string, Bounds][]).map(([key, [min, max]]) => [
    key,
    bounded(min, max),
  ]),
) as Partial<Record<keyof SleepFormValues, Validator<string>>>

const { values, errors, isSubmitting, handleSubmit, handleBlur, validateField, reset } =
  useForm<SleepFormValues>({
    initialValues: defaultValues(),
    validators: {
      ...boundedValidators,
      date: required<string>(t('health.sleep.form.dateRequired')),
      // Total sleep is required: at least one of hours/minutes must be present.
      totalHours: compose<string>(
        (): string | null =>
          hmToSeconds(values.totalHours, values.totalMinutes) === null
            ? t('health.sleep.form.totalSleepRequired')
            : null,
        bounded(0),
        stagesWithinTotal,
      ),
      // Sleep start must precede sleep end when both times are provided.
      sleepEndTimeLocal: (end: string): string | null =>
        values.sleepStartTimeLocal && end && values.sleepStartTimeLocal >= end
          ? t('health.sleep.form.endBeforeStart')
          : null,
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.sleep.form.editTitle') : t('health.sleep.form.addTitle'),
)

/** Hours/minutes pairs of the stage breakdown, in display order. */
const durationFields = [
  { label: 'deep', hours: 'deepHours', minutes: 'deepMinutes' },
  { label: 'light', hours: 'lightHours', minutes: 'lightMinutes' },
  { label: 'rem', hours: 'remHours', minutes: 'remMinutes' },
  { label: 'awake', hours: 'awakeHours', minutes: 'awakeMinutes' },
] as const

/** Plain number inputs per collapsible section. */
const heartRateFields = [
  'restingHeartRate',
  'avgHeartRate',
  'minHeartRate',
  'maxHeartRate',
] as const
const bloodOxygenFields = ['spo2', 'lowestSpo2', 'highestSpo2'] as const
const metricsFields = ['sleepScore', 'avgSleepStress'] as const

/** Fields whose error forces their collapsible section open. */
const sectionFields = {
  times: ['sleepEndTimeLocal'],
  breakdown: [...durationFields.flatMap((f) => [f.hours, f.minutes]), 'awakeCount'],
  heartRate: [...heartRateFields],
  bloodOxygen: [...bloodOxygenFields],
  metrics: [...metricsFields],
} as const satisfies Record<string, readonly (keyof SleepFormValues)[]>

type SectionName = keyof typeof sectionFields | 'stages'

const openSections = reactive<Record<SectionName, boolean>>({
  times: false,
  breakdown: false,
  heartRate: false,
  bloodOxygen: false,
  metrics: false,
  stages: false,
})

/** Error message for the first failing field of an hours/minutes pair. */
function pairError(
  hours: keyof SleepFormValues,
  minutes: keyof SleepFormValues,
): string | undefined {
  return errors.value[hours] ?? errors.value[minutes]
}

/** Validates both halves of an hours/minutes pair once either loses focus. */
function blurPair(hours: keyof SleepFormValues, minutes: keyof SleepFormValues): void {
  handleBlur(hours)
  handleBlur(minutes)
  if (hmToSeconds(values.totalHours, values.totalMinutes) !== null) {
    validateField('totalHours')
  }
}

/** Validates the end time too, since its rule depends on the start time. */
function blurStart(): void {
  if (values.sleepEndTimeLocal) {
    validateField('sleepEndTimeLocal')
  }
}

/** Per-row stage duration errors; stage rows live outside the form values. */
const stageErrors = computed(() =>
  stages.value.map((row) => {
    const hours = bounded(0)(row.durationHours)
    return hours ?? bounded(0, MAX_MINUTES)(row.durationMinutes)
  }),
)

watch(
  () => stageErrors.value.some(Boolean),
  (hasError) => {
    if (hasError) {
      openSections.stages = true
    }
  },
)

for (const [name, fields] of Object.entries(sectionFields) as [
  keyof typeof sectionFields,
  readonly (keyof SleepFormValues)[],
][]) {
  watch(
    () => fields.some((field) => errors.value[field]),
    (hasError) => {
      if (hasError) {
        openSections[name] = true
      }
    },
  )
}

/** Seeds the form from the entry being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  stages.value = []
  for (const name of Object.keys(openSections) as SectionName[]) {
    openSections[name] = false
  }
  const entry = props.entry
  if (!entry) {
    values.date = todayIsoDate()
    return
  }
  values.date = entry.date ?? todayIsoDate()
  values.sleepStartTimeLocal = toDateTimeLocal(entry.sleepStartTimeLocal)
  values.sleepEndTimeLocal = toDateTimeLocal(entry.sleepEndTimeLocal)
  const total = secondsToHm(entry.totalSleepSeconds)
  values.totalHours = total.hours
  values.totalMinutes = total.minutes
  const deep = secondsToHm(entry.deepSleepSeconds)
  values.deepHours = deep.hours
  values.deepMinutes = deep.minutes
  const light = secondsToHm(entry.lightSleepSeconds)
  values.lightHours = light.hours
  values.lightMinutes = light.minutes
  const rem = secondsToHm(entry.remSleepSeconds)
  values.remHours = rem.hours
  values.remMinutes = rem.minutes
  const awake = secondsToHm(entry.awakeSleepSeconds)
  values.awakeHours = awake.hours
  values.awakeMinutes = awake.minutes
  values.awakeCount = entry.awakeCount !== null ? String(entry.awakeCount) : ''
  values.sleepScore = entry.sleepScoreOverall !== null ? String(entry.sleepScoreOverall) : ''
  values.restingHeartRate = entry.restingHeartRate !== null ? String(entry.restingHeartRate) : ''
  values.avgHeartRate = entry.avgHeartRate !== null ? String(entry.avgHeartRate) : ''
  values.minHeartRate = entry.minHeartRate !== null ? String(entry.minHeartRate) : ''
  values.maxHeartRate = entry.maxHeartRate !== null ? String(entry.maxHeartRate) : ''
  values.skinTempDeviation =
    entry.avgSkinTempDeviation !== null ? String(entry.avgSkinTempDeviation) : ''
  values.spo2 = entry.avgSpo2 !== null ? String(entry.avgSpo2) : ''
  values.lowestSpo2 = entry.lowestSpo2 !== null ? String(entry.lowestSpo2) : ''
  values.highestSpo2 = entry.highestSpo2 !== null ? String(entry.highestSpo2) : ''
  values.avgSleepStress = entry.avgSleepStress !== null ? String(entry.avgSleepStress) : ''
  stages.value = entry.sleepStages.map((stage) => {
    const duration = secondsToHm(stage.durationSeconds)
    return {
      stageType: stage.stageType !== null ? String(stage.stageType) : '0',
      startTimeGmt: toDateTimeLocal(stage.startTimeGmt),
      endTimeGmt: toDateTimeLocal(stage.endTimeGmt),
      durationHours: duration.hours,
      durationMinutes: duration.minutes,
    }
  })
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
    :description="t('health.sleep.form.description')"
    :submit-label="isEditing ? t('health.sleep.form.save') : t('health.sleep.form.create')"
    :cancel-label="t('health.sleep.form.cancel')"
    :close-label="t('health.sleep.form.close')"
    :submitting="isSubmitting"
    content-class="max-w-2xl"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField :label="t('health.sleep.form.date')" :error="errors.date" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.date"
            :class="fieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="date"
            :max="todayIsoDate()"
            :disabled="isSubmitting"
            @blur="handleBlur('date')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('health.sleep.form.totalSleep')"
        :error="pairError('totalHours', 'totalMinutes')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <div class="flex items-center gap-1">
            <input
              :id="fieldId"
              v-model="values.totalHours"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="t('health.sleep.form.hours')"
              type="number"
              min="0"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="blurPair('totalHours', 'totalMinutes')"
            />
            <span class="text-hint">h</span>
            <input
              v-model="values.totalMinutes"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              :placeholder="t('health.sleep.form.minutes')"
              type="number"
              min="0"
              max="59"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="blurPair('totalHours', 'totalMinutes')"
            />
            <span class="text-hint">m</span>
          </div>
        </template>
      </FormField>
    </div>

    <details :class="sectionClass" :open="openSections.times" @toggle="onToggle('times', $event)">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.sleepTimes') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.sleep.form.startTime')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.sleepStartTimeLocal"
              :class="fieldClass"
              type="datetime-local"
              :max="todayDateTimeLocalMax()"
              :disabled="isSubmitting"
              @blur="blurStart"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.endTime')" :error="errors.sleepEndTimeLocal">
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values.sleepEndTimeLocal"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="datetime-local"
              :max="todayDateTimeLocalMax()"
              :disabled="isSubmitting"
              @blur="handleBlur('sleepEndTimeLocal')"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details
      :class="sectionClass"
      :open="openSections.breakdown"
      @toggle="onToggle('breakdown', $event)"
    >
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.stageBreakdown') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          v-for="field in durationFields"
          :key="field.label"
          :label="t(`health.sleep.form.${field.label}`)"
          :error="pairError(field.hours, field.minutes)"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <div class="flex items-center gap-1">
              <input
                :id="fieldId"
                v-model="values[field.hours]"
                :class="fieldClass"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                :placeholder="t('health.sleep.form.hours')"
                type="number"
                min="0"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
                @blur="blurPair(field.hours, field.minutes)"
              />
              <span class="text-hint">h</span>
              <input
                v-model="values[field.minutes]"
                :class="fieldClass"
                :aria-describedby="describedBy"
                :aria-invalid="invalid"
                :placeholder="t('health.sleep.form.minutes')"
                type="number"
                min="0"
                max="59"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
                @blur="blurPair(field.hours, field.minutes)"
              />
              <span class="text-hint">m</span>
            </div>
          </template>
        </FormField>

        <FormField
          v-for="key in ['awakeCount' as const]"
          :key="key"
          :label="t(`health.sleep.form.${key}`)"
          :error="errors[key]"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values[key]"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="number"
              :min="boundedFields[key][0]"
              :max="boundedFields[key][1]"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="handleBlur(key)"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details
      :class="sectionClass"
      :open="openSections.heartRate"
      @toggle="onToggle('heartRate', $event)"
    >
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.heartRate') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          v-for="key in heartRateFields"
          :key="key"
          :label="t(`health.sleep.form.${key}`)"
          :error="errors[key]"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values[key]"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="number"
              :min="boundedFields[key][0]"
              :max="boundedFields[key][1]"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="handleBlur(key)"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details
      :class="sectionClass"
      :open="openSections.bloodOxygen"
      @toggle="onToggle('bloodOxygen', $event)"
    >
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.bloodOxygen') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          v-for="key in bloodOxygenFields"
          :key="key"
          :label="t(`health.sleep.form.${key}`)"
          :error="errors[key]"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values[key]"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="number"
              :min="boundedFields[key][0]"
              :max="boundedFields[key][1]"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="handleBlur(key)"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details
      :class="sectionClass"
      :open="openSections.metrics"
      @toggle="onToggle('metrics', $event)"
    >
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.metrics') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          v-for="key in metricsFields"
          :key="key"
          :label="t(`health.sleep.form.${key}`)"
          :error="errors[key]"
        >
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values[key]"
              :class="fieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="number"
              :min="boundedFields[key][0]"
              :max="boundedFields[key][1]"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
              @blur="handleBlur(key)"
            />
          </template>
        </FormField>

        <FormField
          :label="t('health.sleep.form.skinTempDeviation')"
          :placeholder="t('health.sleep.form.skinTempDeviation')"
        >
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.skinTempDeviation"
              :class="fieldClass"
              :placeholder="placeholder"
              type="number"
              step="0.1"
              inputmode="decimal"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details :class="sectionClass" :open="openSections.stages" @toggle="onToggle('stages', $event)">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.sleepStages') }}
      </summary>
      <div class="mt-2 flex flex-col gap-3">
        <p v-if="stages.length === 0" class="text-hint">
          {{ t('health.sleep.form.noStages') }}
        </p>
        <div
          v-for="(stage, index) in stages"
          :key="index"
          class="flex flex-col gap-2 rounded-input border border-border p-2"
        >
          <div class="flex items-center justify-between">
            <span class="text-caption">
              {{ t('health.sleep.form.stageLabel', { index: index + 1 }) }}
            </span>
            <Button
              type="button"
              variant="ghostDestructive"
              size="icon-sm"
              :aria-label="t('health.sleep.form.removeStage')"
              :disabled="isSubmitting"
              @click="removeStage(index)"
            >
              <Trash2 class="size-4" aria-hidden="true" />
            </Button>
          </div>
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <FormField :label="t('health.sleep.form.stageType')">
              <template #default="{ fieldId }">
                <select
                  :id="fieldId"
                  v-model="stage.stageType"
                  :class="fieldClass"
                  :disabled="isSubmitting"
                >
                  <option value="0">{{ t('health.sleep.form.stageDeep') }}</option>
                  <option value="1">{{ t('health.sleep.form.stageLight') }}</option>
                  <option value="2">{{ t('health.sleep.form.stageRem') }}</option>
                  <option value="3">{{ t('health.sleep.form.stageAwake') }}</option>
                </select>
              </template>
            </FormField>

            <FormField
              :label="t('health.sleep.form.stageDuration')"
              :error="stageErrors[index] ?? undefined"
            >
              <template #default="{ fieldId, describedBy, invalid }">
                <div class="flex items-center gap-1">
                  <input
                    :id="fieldId"
                    v-model="stage.durationHours"
                    :class="fieldClass"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                    :placeholder="t('health.sleep.form.hours')"
                    type="number"
                    min="0"
                    step="1"
                    inputmode="numeric"
                    :disabled="isSubmitting"
                  />
                  <span class="text-hint">h</span>
                  <input
                    v-model="stage.durationMinutes"
                    :class="fieldClass"
                    :aria-describedby="describedBy"
                    :aria-invalid="invalid"
                    :placeholder="t('health.sleep.form.minutes')"
                    type="number"
                    min="0"
                    max="59"
                    step="1"
                    inputmode="numeric"
                    :disabled="isSubmitting"
                  />
                  <span class="text-hint">m</span>
                </div>
              </template>
            </FormField>

            <FormField :label="t('health.sleep.form.stageStart')">
              <template #default="{ fieldId }">
                <input
                  :id="fieldId"
                  v-model="stage.startTimeGmt"
                  :class="fieldClass"
                  type="datetime-local"
                  :disabled="isSubmitting"
                />
              </template>
            </FormField>

            <FormField :label="t('health.sleep.form.stageEnd')">
              <template #default="{ fieldId }">
                <input
                  :id="fieldId"
                  v-model="stage.endTimeGmt"
                  :class="fieldClass"
                  type="datetime-local"
                  :disabled="isSubmitting"
                />
              </template>
            </FormField>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          class="gap-1 self-start"
          :disabled="isSubmitting"
          @click="addStage"
        >
          <Plus class="size-4" aria-hidden="true" />
          {{ t('health.sleep.form.addStage') }}
        </Button>
      </div>
    </details>
  </FormDialog>
</template>
