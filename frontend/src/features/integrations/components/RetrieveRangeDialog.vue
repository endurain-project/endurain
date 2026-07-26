<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DateRange } from '@/features/integrations/types'

import { Button } from '@/components/ui/button'
import { FormDialog } from '@/components/ui/form-dialog'
import { inputFieldClass } from '@/components/ui/input/fieldClasses'
import { Label } from '@/components/ui/label'
import { daysAgoRange } from '@/features/integrations/utils/dateRange'
import { todayIsoDate } from '@/utils/datetime'

const open = defineModel<boolean>('open', { required: true })

defineProps<{
  /** Dialog heading (provided by the caller per data type). */
  title: string
  /** Whether the retrieve request is in flight. */
  pending: boolean
}>()

const emit = defineEmits<{
  submit: [range: DateRange]
}>()

const { t } = useI18n()

type Mode = 'days' | 'range'
const mode = ref<Mode>('days')
const days = ref('7')
const startDate = ref('')
const endDate = ref('')

// The viewer's local calendar day: bounding the pickers by the UTC day stopped
// users east of UTC selecting today, and let those far west select tomorrow.
const today = computed(() => todayIsoDate())

const canSubmit = computed(() => {
  if (mode.value === 'days') {
    const parsed = Number(days.value)
    return Number.isFinite(parsed) && parsed > 0
  }
  return startDate.value !== '' && endDate.value !== '' && startDate.value <= endDate.value
})

// Reset to the default "last 7 days" each time the dialog opens.
watch(open, (isOpen) => {
  if (isOpen) {
    mode.value = 'days'
    days.value = '7'
    startDate.value = ''
    endDate.value = ''
  }
})

/** Resolves the selected mode to a concrete window and emits it. */
function onSubmit(): void {
  const range =
    mode.value === 'days'
      ? daysAgoRange(Number(days.value))
      : { startDate: startDate.value, endDate: endDate.value }
  emit('submit', range)
}
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="title"
    :description="t('settings.integrations.retrieve.description')"
    :submit-label="t('settings.integrations.retrieve.submit')"
    :cancel-label="t('settings.integrations.cancel')"
    :close-label="t('settings.integrations.close')"
    :submitting="pending"
    :can-submit="canSubmit"
    @submit="onSubmit"
  >
    <div class="flex flex-col gap-3">
      <div class="flex gap-2">
        <Button
          type="button"
          :variant="mode === 'days' ? 'default' : 'outline'"
          size="sm"
          class="flex-1"
          @click="mode = 'days'"
        >
          {{ t('settings.integrations.retrieve.modeDays') }}
        </Button>
        <Button
          type="button"
          :variant="mode === 'range' ? 'default' : 'outline'"
          size="sm"
          class="flex-1"
          @click="mode = 'range'"
        >
          {{ t('settings.integrations.retrieve.modeRange') }}
        </Button>
      </div>

      <div v-if="mode === 'days'" class="flex flex-col gap-1.5">
        <Label for="retrieve-days">{{ t('settings.integrations.retrieve.days') }}</Label>
        <input
          id="retrieve-days"
          v-model="days"
          type="number"
          min="1"
          :disabled="pending"
          :class="inputFieldClass"
        />
      </div>

      <div v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div class="flex flex-col gap-1.5">
          <Label for="retrieve-start">{{ t('settings.integrations.retrieve.startDate') }}</Label>
          <input
            id="retrieve-start"
            v-model="startDate"
            type="date"
            :max="today"
            :disabled="pending"
            :class="inputFieldClass"
          />
        </div>
        <div class="flex flex-col gap-1.5">
          <Label for="retrieve-end">{{ t('settings.integrations.retrieve.endDate') }}</Label>
          <input
            id="retrieve-end"
            v-model="endDate"
            type="date"
            :max="today"
            :disabled="pending"
            :class="inputFieldClass"
          />
        </div>
      </div>
    </div>
  </FormDialog>
</template>
