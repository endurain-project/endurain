<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  Goal,
  GoalActivityType,
  GoalInput,
  GoalInterval,
  GoalMetric,
} from '@/features/goals/types'
import type { Schemas } from '@/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Select } from '@/components/ui/select'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { toNumberOrNull } from '@/utils/number'
import {
  ACTIVITY_TYPE_LABEL_KEYS,
  GOAL_ACTIVITY_TYPES,
  GOAL_INTERVALS,
  GOAL_METRICS,
  GOAL_METRIC_LABEL_KEYS,
  INTERVAL_LABEL_KEYS,
  distanceValueToMeters,
  elevationValueToMeters,
  hoursMinutesToSeconds,
  metersToDistanceValue,
  metersToElevationValue,
  secondsToHoursMinutes,
} from '@/features/goals/utils/goalFormat'
import { useCreateGoalMutation, useUpdateGoalMutation } from '@/features/goals/composables/useGoals'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The goal being edited, or `null`/absent when adding a new one. */
    goal?: Goal | null
    /** The viewer's measurement system, used for the distance/elevation fields. */
    units: Schemas['Units']
  }>(),
  { goal: null },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateGoalMutation()
const updateMutation = useUpdateGoalMutation()

/** Form shape: numeric fields are kept as strings and parsed at submit. */
interface GoalFormValues {
  interval: GoalInterval
  activityType: GoalActivityType
  goalType: GoalMetric
  calories: string
  activitiesNumber: string
  distance: string
  elevation: string
  durationHours: string
  durationMinutes: string
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): GoalFormValues {
  return {
    interval: 'daily',
    activityType: 'run',
    goalType: 'distance',
    calories: '',
    activitiesNumber: '',
    distance: '',
    elevation: '',
    durationHours: '',
    durationMinutes: '',
  }
}

/** Parses a string field to a non-negative integer, or `null` when blank/invalid. */
function toIntOrNull(value: string): number | null {
  const parsed = toNumberOrNull(value)
  return parsed === null ? null : Math.round(parsed)
}

/**
 * Resolves the target for the currently-selected metric into the backend's base
 * unit (kcal, count, metres or seconds), or `null` when the field is empty.
 *
 * @param values - The current form values.
 * @returns The target in base units, or `null`.
 */
function targetBaseUnits(values: GoalFormValues): number | null {
  switch (values.goalType) {
    case 'calories':
      return toIntOrNull(values.calories)
    case 'activities':
      return toIntOrNull(values.activitiesNumber)
    case 'distance': {
      const parsed = toNumberOrNull(values.distance)
      return parsed === null ? null : distanceValueToMeters(parsed, props.units)
    }
    case 'elevation': {
      const parsed = toNumberOrNull(values.elevation)
      return parsed === null ? null : elevationValueToMeters(parsed, props.units)
    }
    case 'duration': {
      const seconds = hoursMinutesToSeconds(
        toNumberOrNull(values.durationHours) ?? 0,
        toNumberOrNull(values.durationMinutes) ?? 0,
      )
      return seconds > 0 ? seconds : null
    }
  }
  return null
}

/** Projects the form values onto the clean {@link GoalInput}. */
function buildInput(values: GoalFormValues): GoalInput {
  const base = targetBaseUnits(values)
  return {
    interval: values.interval,
    activityType: values.activityType,
    goalType: values.goalType,
    calories: values.goalType === 'calories' ? base : null,
    activitiesNumber: values.goalType === 'activities' ? base : null,
    distanceMeters: values.goalType === 'distance' ? base : null,
    elevationMeters: values.goalType === 'elevation' ? base : null,
    durationSeconds: values.goalType === 'duration' ? base : null,
  }
}

/**
 * Persists the goal, emitting the outcome to the parent and closing on success.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: GoalFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    if (props.goal) {
      await updateMutation.mutateAsync({ id: props.goal.id, input, version: props.goal.version })
      emit('success', t('settings.goals.form.updateSuccess'))
    } else {
      await createMutation.mutateAsync(input)
      emit('success', t('settings.goals.form.createSuccess'))
    }
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('settings.goals.form.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<GoalFormValues>({
  initialValues: defaultValues(),
  onSubmit: submitForm,
})

const isEditing = computed(() => props.goal !== null)
const dialogTitle = computed(() =>
  isEditing.value ? t('settings.goals.form.editTitle') : t('settings.goals.form.addTitle'),
)

/** A goal needs a positive target for its selected metric before it can be saved. */
const canSubmit = computed(() => {
  const base = targetBaseUnits(values)
  return base !== null && base > 0
})

const distanceUnit = computed(() =>
  props.units === 'imperial' ? t('settings.goals.unit.miles') : t('settings.goals.unit.km'),
)
const elevationUnit = computed(() =>
  props.units === 'imperial' ? t('settings.goals.unit.feet') : t('settings.goals.unit.meters'),
)
const distanceLabel = computed(
  () => `${t('settings.goals.metric.distance')} (${distanceUnit.value})`,
)
const elevationLabel = computed(
  () => `${t('settings.goals.metric.elevation')} (${elevationUnit.value})`,
)
const caloriesLabel = computed(
  () => `${t('settings.goals.metric.calories')} (${t('settings.goals.unit.calories')})`,
)

/** Seeds the form from the goal being edited, or pristine defaults. */
function populate(): void {
  reset()
  const goal = props.goal
  if (!goal) {
    return
  }
  values.interval = goal.interval
  values.activityType = goal.activityType
  values.goalType = goal.goalType
  values.calories = goal.calories !== null ? String(goal.calories) : ''
  values.activitiesNumber = goal.activitiesNumber !== null ? String(goal.activitiesNumber) : ''
  values.distance =
    goal.distanceMeters !== null
      ? String(metersToDistanceValue(goal.distanceMeters, props.units))
      : ''
  values.elevation =
    goal.elevationMeters !== null
      ? String(metersToElevationValue(goal.elevationMeters, props.units))
      : ''
  if (goal.durationSeconds !== null) {
    const { hours, minutes } = secondsToHoursMinutes(goal.durationSeconds)
    values.durationHours = String(hours)
    values.durationMinutes = String(minutes)
  }
}

// Re-seed each time the dialog opens; the parent sets `goal` before opening.
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
    :description="t('settings.goals.form.description')"
    :submit-label="isEditing ? t('settings.goals.form.save') : t('settings.goals.form.create')"
    :cancel-label="t('settings.goals.form.cancel')"
    :close-label="t('settings.goals.form.close')"
    :submitting="isSubmitting"
    :can-submit="canSubmit"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-2">
      <FormField :label="t('settings.goals.form.interval')" required>
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.interval" :disabled="isSubmitting">
            <option v-for="value in GOAL_INTERVALS" :key="value" :value="value">
              {{ t(INTERVAL_LABEL_KEYS[value]) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.goals.form.activityType')" required>
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.activityType" :disabled="isSubmitting">
            <option v-for="value in GOAL_ACTIVITY_TYPES" :key="value" :value="value">
              {{ t(ACTIVITY_TYPE_LABEL_KEYS[value]) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField class="sm:col-span-2" :label="t('settings.goals.form.metric')" required>
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.goalType" :disabled="isSubmitting">
            <option v-for="value in GOAL_METRICS" :key="value" :value="value">
              {{ t(GOAL_METRIC_LABEL_KEYS[value]) }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField
        v-if="values.goalType === 'calories'"
        class="sm:col-span-2"
        :label="caloriesLabel"
        required
      >
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.calories"
            :class="inputFieldClass"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField
        v-else-if="values.goalType === 'activities'"
        class="sm:col-span-2"
        :label="t('settings.goals.metric.activities')"
        required
      >
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.activitiesNumber"
            :class="inputFieldClass"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField
        v-else-if="values.goalType === 'distance'"
        class="sm:col-span-2"
        :label="distanceLabel"
        required
      >
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.distance"
            :class="inputFieldClass"
            type="number"
            min="0"
            step="0.1"
            inputmode="decimal"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <FormField
        v-else-if="values.goalType === 'elevation'"
        class="sm:col-span-2"
        :label="elevationLabel"
        required
      >
        <template #default="{ fieldId }">
          <input
            :id="fieldId"
            v-model="values.elevation"
            :class="inputFieldClass"
            type="number"
            min="0"
            step="1"
            inputmode="numeric"
            :disabled="isSubmitting"
          />
        </template>
      </FormField>

      <template v-else-if="values.goalType === 'duration'">
        <FormField :label="t('settings.goals.form.durationHours')" required>
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.durationHours"
              :class="inputFieldClass"
              type="number"
              min="0"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
        <FormField :label="t('settings.goals.form.durationMinutes')" required>
          <template #default="{ fieldId }">
            <input
              :id="fieldId"
              v-model="values.durationMinutes"
              :class="inputFieldClass"
              type="number"
              min="0"
              max="59"
              step="1"
              inputmode="numeric"
              :disabled="isSubmitting"
            />
          </template>
        </FormField>
      </template>
    </div>
  </FormDialog>
</template>
