<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Trash2 } from '@lucide/vue'

import type { SleepEntry, SleepEntryInput, SleepStage } from '@/features/health/types'

import { Button } from '@/components/ui/button'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { todayIsoDate } from '@/utils/datetime'
import { toNumberOrNull } from '@/utils/number'
import { required } from '@/utils/validators'
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
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.sleep.form.saveError'))
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<SleepFormValues>({
    initialValues: defaultValues(),
    validators: {
      date: required<string>(t('health.sleep.form.dateRequired')),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.entry !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('health.sleep.form.editTitle') : t('health.sleep.form.addTitle'),
)

/** Total sleep is required: at least one of hours/minutes must be present. */
const hasTotal = computed(() => hmToSeconds(values.totalHours, values.totalMinutes) !== null)

/** Sleep start must precede sleep end when both times are provided. */
const timesValid = computed(() => {
  const start = values.sleepStartTimeLocal
  const end = values.sleepEndTimeLocal
  if (!start || !end) {
    return true
  }
  return start < end
})

/** Inline error for the end-time field, or `undefined` when valid. */
const endTimeError = computed(() =>
  timesValid.value ? undefined : t('health.sleep.form.endBeforeStart'),
)

const canSubmit = computed(() => isValid.value && hasTotal.value && timesValid.value)

/** Seeds the form from the entry being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  stages.value = []
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
    :can-submit="canSubmit"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <FormField :label="t('health.sleep.form.date')" :error="errors.date" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <input
            :id="fieldId"
            v-model="values.date"
            :class="inputFieldClass"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            type="date"
            :disabled="isSubmitting"
            @blur="handleBlur('date')"
          />
        </template>
      </FormField>

      <FormField :label="t('health.sleep.form.totalSleep')" required>
        <template #default="{ fieldId }">
          <div class="flex items-center gap-1">
            <input
              :id="fieldId"
              v-model="values.totalHours"
              :class="inputFieldClass"
              :placeholder="t('health.sleep.form.hours')"
              type="number"
              min="0"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
            <span class="text-hint">h</span>
            <input
              v-model="values.totalMinutes"
              :class="inputFieldClass"
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
    </div>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.sleepTimes') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.sleep.form.startTime')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.sleepStartTimeLocal"
              :class="inputFieldClass"
              type="datetime-local"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.endTime')" :error="endTimeError">
          <template #default="{ fieldId, describedBy, invalid }">
            <input
              :id="fieldId"
              v-model="values.sleepEndTimeLocal"
              :class="inputFieldClass"
              :aria-describedby="describedBy"
              :aria-invalid="invalid"
              type="datetime-local"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.stageBreakdown') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.sleep.form.deep')">
          <template #default="{ fieldId }">
            <div class="flex items-center gap-1">
              <input
                :id="fieldId"
                v-model="values.deepHours"
                :class="inputFieldClass"
                :placeholder="t('health.sleep.form.hours')"
                type="number"
                min="0"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
              />
              <span class="text-hint">h</span>
              <input
                v-model="values.deepMinutes"
                :class="inputFieldClass"
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

        <FormField :label="t('health.sleep.form.light')">
          <template #default="{ fieldId }">
            <div class="flex items-center gap-1">
              <input
                :id="fieldId"
                v-model="values.lightHours"
                :class="inputFieldClass"
                :placeholder="t('health.sleep.form.hours')"
                type="number"
                min="0"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
              />
              <span class="text-hint">h</span>
              <input
                v-model="values.lightMinutes"
                :class="inputFieldClass"
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

        <FormField :label="t('health.sleep.form.rem')">
          <template #default="{ fieldId }">
            <div class="flex items-center gap-1">
              <input
                :id="fieldId"
                v-model="values.remHours"
                :class="inputFieldClass"
                :placeholder="t('health.sleep.form.hours')"
                type="number"
                min="0"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
              />
              <span class="text-hint">h</span>
              <input
                v-model="values.remMinutes"
                :class="inputFieldClass"
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

        <FormField :label="t('health.sleep.form.awake')">
          <template #default="{ fieldId }">
            <div class="flex items-center gap-1">
              <input
                :id="fieldId"
                v-model="values.awakeHours"
                :class="inputFieldClass"
                :placeholder="t('health.sleep.form.hours')"
                type="number"
                min="0"
                step="1"
                inputmode="numeric"
                :disabled="isSubmitting"
              />
              <span class="text-hint">h</span>
              <input
                v-model="values.awakeMinutes"
                :class="inputFieldClass"
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

        <FormField :label="t('health.sleep.form.awakeCount')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.awakeCount"
              :class="inputFieldClass"
              type="number"
              min="0"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.heartRate') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          :label="t('health.sleep.form.restingHeartRate')"
          :placeholder="t('health.sleep.form.restingHeartRate')"
        >
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.restingHeartRate"
              :class="inputFieldClass"
              :placeholder="placeholder"
              type="number"
              min="20"
              max="220"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.avgHeartRate')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.avgHeartRate"
              :class="inputFieldClass"
              type="number"
              min="20"
              max="220"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.minHeartRate')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.minHeartRate"
              :class="inputFieldClass"
              type="number"
              min="20"
              max="220"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.maxHeartRate')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.maxHeartRate"
              :class="inputFieldClass"
              type="number"
              min="20"
              max="220"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.bloodOxygen') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField :label="t('health.sleep.form.spo2')" :placeholder="t('health.sleep.form.spo2')">
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.spo2"
              :class="inputFieldClass"
              :placeholder="placeholder"
              type="number"
              min="70"
              max="100"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.lowestSpo2')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.lowestSpo2"
              :class="inputFieldClass"
              type="number"
              min="70"
              max="100"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.highestSpo2')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.highestSpo2"
              :class="inputFieldClass"
              type="number"
              min="70"
              max="100"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </div>
    </details>

    <details class="mt-2 rounded-input border border-border px-3 py-2">
      <summary class="cursor-pointer text-caption select-none">
        {{ t('health.sleep.form.metrics') }}
      </summary>
      <div class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <FormField
          :label="t('health.sleep.form.sleepScore')"
          :placeholder="t('health.sleep.form.sleepScore')"
        >
          <template #default="{ fieldId, placeholder }">
            <input
              :id="fieldId"
              v-model="values.sleepScore"
              :class="inputFieldClass"
              :placeholder="placeholder"
              type="number"
              min="0"
              max="100"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>

        <FormField :label="t('health.sleep.form.avgSleepStress')">
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.avgSleepStress"
              :class="inputFieldClass"
              type="number"
              min="0"
              max="100"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
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
              :class="inputFieldClass"
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

    <details class="mt-2 rounded-input border border-border px-3 py-2">
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
                  :class="inputFieldClass"
                  :disabled="isSubmitting"
                >
                  <option value="0">{{ t('health.sleep.form.stageDeep') }}</option>
                  <option value="1">{{ t('health.sleep.form.stageLight') }}</option>
                  <option value="2">{{ t('health.sleep.form.stageRem') }}</option>
                  <option value="3">{{ t('health.sleep.form.stageAwake') }}</option>
                </select>
              </template>
            </FormField>

            <FormField :label="t('health.sleep.form.stageDuration')">
              <template #default="{ fieldId }">
                <div class="flex items-center gap-1">
                  <input
                    :id="fieldId"
                    v-model="stage.durationHours"
                    :class="inputFieldClass"
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
                    :class="inputFieldClass"
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
                  :class="inputFieldClass"
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
                  :class="inputFieldClass"
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
