<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Gear } from '@/features/gears/types'

import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useGearActivitiesQuery } from '@/features/gears/composables/useGearActivities'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  /** The gear to delete; `null` while none is selected. */
  gear: Gear | null
  /** Whether the delete is in flight. */
  pending: boolean
  /** How many components the gear has, when the caller already loaded them. */
  componentCount?: number
}>()

defineEmits<{
  /** The user confirmed the deletion. */
  confirm: []
}>()

const { t } = useI18n()

// One record is enough: only the page's `total` is read, and only while the dialog is open.
const activitiesQuery = useGearActivitiesQuery(
  () => (open.value ? (props.gear?.id ?? null) : null),
  1,
  1,
)
const activityCount = computed(() => activitiesQuery.data.value?.total ?? 0)

/** The confirmation text plus what deleting does to the gear's activities and components. */
const description = computed(() => {
  const parts = [t('gears.delete.body', { nickname: props.gear?.nickname ?? '' })]
  if (activityCount.value > 0) {
    parts.push(t('gears.delete.activities', { count: activityCount.value }))
  }
  if (props.componentCount) {
    parts.push(t('gears.delete.components', { count: props.componentCount }))
  }
  return parts.join(' ')
})
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    :title="t('gears.delete.title')"
    :description="description"
    :confirm-label="t('gears.delete.confirm')"
    :cancel-label="t('gears.delete.cancel')"
    :close-label="t('gears.delete.close')"
    :pending="pending"
    @confirm="$emit('confirm')"
  />
</template>
