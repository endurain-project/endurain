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
import { flOzToMl, mlToFlOz } from '@/utils/units'
import { useUpdateWaterTargetMutation } from '@/features/health/composables/useHealth'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The current health targets, providing the record id, owner, and water target. */
  targets: HealthTargets
  /** The viewer's measurement system, used for the amount field units. */
  units: Schemas['Units']
}>()

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const updateTargetMutation = useUpdateWaterTargetMutation()

/** Form shape: the numeric target is kept as a string and parsed at submit. */
interface TargetFormValues {
  amount: string
}

/** Whether the viewer enters volumes in US fluid ounces rather than millilitres. */
const isImperial = computed(() => props.units === 'imperial')

/** Converts the target string to whole millilitres (or `null` to clear). */
function targetToMl(raw: string): number | null {
  const value = toNumberOrNull(raw)
  if (value === null || value <= 0) {
    return null
  }
  return Math.round(isImperial.value ? flOzToMl(value) : value)
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
      waterMl: targetToMl(values.amount),
    })
    emit('success', t('health.water.target.saveSuccess'))
    open.value = false
  } catch (error) {
    emit('error', isStaleWrite(error) ? t('app.staleError') : t('health.water.target.saveError'))
  }
}

const { values, isSubmitting, handleSubmit, reset } = useForm<TargetFormValues>({
  initialValues: { amount: '' },
  onSubmit: submitForm,
})

const amountUnitLabel = computed(() => (isImperial.value ? 'fl oz' : 'ml'))
const amountLabel = computed(() => `${t('health.water.target.amount')} (${amountUnitLabel.value})`)

/** Seeds the field from the current target each time the dialog opens. */
function populate(): void {
  reset()
  const ml = props.targets.waterMl
  if (ml === null) {
    values.amount = ''
    return
  }
  values.amount = String(isImperial.value ? Math.round(mlToFlOz(ml) * 10) / 10 : Math.round(ml))
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
    :title="t('health.water.target.title')"
    :description="t('health.water.target.description')"
    :submit-label="t('health.water.target.save')"
    :cancel-label="t('health.water.target.cancel')"
    :close-label="t('health.water.target.close')"
    :submitting="isSubmitting"
    @submit="handleSubmit"
  >
    <FormField
      :label="amountLabel"
      :placeholder="amountLabel"
      :hint="t('health.water.target.hint')"
    >
      <template #default="{ fieldId, placeholder }">
        <input
          :id="fieldId"
          v-model="values.amount"
          :class="inputFieldClass"
          :placeholder="placeholder"
          type="number"
          min="0"
          step="any"
          inputmode="decimal"
          :disabled="isSubmitting"
        />
      </template>
    </FormField>
  </FormDialog>
</template>
