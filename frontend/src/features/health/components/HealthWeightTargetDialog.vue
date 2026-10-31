<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Schemas } from '@/types'
import type { HealthTargets } from '@/features/health/types'

import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { useForm } from '@/composables/useForm'
import { isStaleWrite } from '@/services/ifMatch'
import { toNumberOrNull } from '@/utils/number'
import { kgToLbs, lbsToKg } from '@/utils/units'
import { useUpdateWeightTargetMutation } from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The current health targets, providing the record id, owner, and weight. */
  targets: HealthTargets
  /** The viewer's measurement system, used for the target field unit. */
  units: Schemas['Units']
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const updateTargetMutation = useUpdateWeightTargetMutation()

/** Form shape: the numeric target is kept as a string and parsed at submit. */
interface TargetFormValues {
  weight: string
}

/** Renders the stored kg target in the viewer's units for the form input. */
function displayMassFromKg(kg: number | null): string {
  if (kg === null) {
    return ''
  }
  const value = props.units === 'imperial' ? kgToLbs(kg) : kg
  return String(Math.round(value * 100) / 100)
}

/** Converts the display-unit target string back to kilograms (or `null` to clear). */
function targetToKg(raw: string): number | null {
  const value = toNumberOrNull(raw)
  if (value === null || value <= 0) {
    return null
  }
  const kg = props.units === 'imperial' ? lbsToKg(value) : value
  return Math.round(kg * 1000) / 1000
}

/**
 * Persists the target, emitting the outcome to the parent and closing on
 * success. An empty field clears the target (sends `null`).
 *
 * @param values - The form values.
 */
async function submitForm(values: TargetFormValues): Promise<void> {
  try {
    await updateTargetMutation.mutateAsync({
      version: props.targets.version,
      weightKg: targetToKg(values.weight),
    })
    emit('success', t('health.weight.target.saveSuccess'))
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.weight.target.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<TargetFormValues>({
  initialValues: { weight: '' },
  onSubmit: submitForm,
})

const massUnitLabel = computed(() => (props.units === 'imperial' ? 'lb' : 'kg'))
const weightLabel = computed(() => `${t('health.weight.target.weight')} (${massUnitLabel.value})`)

/** Seeds the field from the current target each time the dialog opens. */
function populate(): void {
  reset()
  values.weight = displayMassFromKg(props.targets.weightKg)
}

watch(open, (isOpen) => {
  if (isOpen) {
    populate()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="t('health.weight.target.title')"
    :description="t('health.weight.target.description')"
    :submit-label="t('health.weight.target.save')"
    :cancel-label="t('health.weight.target.cancel')"
    :close-label="t('health.weight.target.close')"
    :submitting="isSubmitting"
    @submit="handleSubmit"
  >
    <FormField
      :label="weightLabel"
      :placeholder="weightLabel"
      :hint="t('health.weight.target.hint')"
    >
      <template #default="{ fieldId, placeholder }">
        <input
          :id="fieldId"
          v-model="values.weight"
          :class="inputFieldClass"
          :placeholder="placeholder"
          type="number"
          min="0"
          step="0.1"
          inputmode="decimal"
          :disabled="isSubmitting"
        />
      </template>
    </FormField>
  </FormDialog>
</template>
