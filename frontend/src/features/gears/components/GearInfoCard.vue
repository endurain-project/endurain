<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { GearDetail } from '@/features/gears/types'
import type { Schemas } from '@/types'

import GearBadges from '@/features/gears/components/GearBadges.vue'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { MetricPill } from '@/components/ui/metric-pill'
import {
  currencySymbol,
  formatDuration,
  metersToDisplayDistance,
} from '@/features/gears/utils/format'

/**
 * The gear-summary card on the gear detail page: status badges, the headline
 * metrics (distance, time, components cost), the descriptive details list, and
 * the edit/delete actions. Purely presentational — it derives its labels from
 * the passed {@link GearDetail} and emits intent to the parent, which owns the
 * edit/delete dialogs.
 */
const props = defineProps<{
  /** The gear, enriched with the detail endpoint's computed totals. */
  gear: GearDetail
  /** The viewer's measurement system, for distance formatting. */
  units: Schemas['Units']
  /** The viewer's currency, for cost formatting. */
  currency: Schemas['Currency']
}>()

const emit = defineEmits<{
  /** The edit action was activated. */
  edit: []
  /** The delete action was activated. */
  delete: []
}>()

const { t, locale } = useI18n()

const distanceUnitLabel = computed(() =>
  props.units === 'imperial' ? t('gears.unitMi') : t('gears.unitKm'),
)
const totalDistance = computed(() => metersToDisplayDistance(props.gear.totalDistance, props.units))
const totalTime = computed(() => formatDuration(props.gear.totalTime))
const componentsCost = computed(
  () =>
    `${currencySymbol(props.currency)}${Math.round(props.gear.totalComponentsCost * 100) / 100}`,
)
const purchaseValueLabel = computed(() =>
  props.gear.purchaseValue !== null && props.gear.purchaseValue !== undefined
    ? `${currencySymbol(props.currency)}${props.gear.purchaseValue}`
    : null,
)
const totalCostLabel = computed(() => {
  if (props.gear.purchaseValue === null || props.gear.purchaseValue === undefined) {
    return null
  }
  const total = Math.round((props.gear.purchaseValue + props.gear.totalComponentsCost) * 100) / 100
  return `${currencySymbol(props.currency)}${total}`
})
const createdAtLabel = computed(() => {
  if (!props.gear.createdAt) {
    return null
  }
  const date = new Date(props.gear.createdAt)
  return Number.isNaN(date.getTime())
    ? null
    : new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeZone: 'UTC' }).format(date)
})
</script>

<template>
  <Card padding="none" class="divide-y divide-border overflow-hidden">
    <div class="flex items-center justify-between gap-2 px-4 py-3">
      <h2 class="text-card-heading">{{ t('gears.form.title') }}</h2>
    </div>
    <div class="flex flex-col gap-3 px-4 py-3">
      <GearBadges :gear="gear" />

      <div class="flex flex-wrap gap-3">
        <MetricPill
          :label="t('gears.detail.totalDistance')"
          :value="totalDistance"
          :unit="distanceUnitLabel"
          accent="brand"
        />
        <MetricPill :label="t('gears.detail.totalTime')" :value="totalTime" accent="effort" />
        <MetricPill :label="t('gears.detail.componentsCost')" :value="componentsCost" />
      </div>

      <dl class="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-1">
        <div v-if="gear.brand" class="flex flex-col gap-0.5">
          <dt class="text-hint">{{ t('gears.form.brand') }}</dt>
          <dd class="text-body">{{ gear.brand }}</dd>
        </div>
        <div v-if="gear.model" class="flex flex-col gap-0.5">
          <dt class="text-hint">{{ t('gears.form.model') }}</dt>
          <dd class="text-body">{{ gear.model }}</dd>
        </div>
        <div v-if="createdAtLabel" class="flex flex-col gap-0.5">
          <dt class="text-hint">{{ t('gears.form.createdAt') }}</dt>
          <dd class="text-body">{{ createdAtLabel }}</dd>
        </div>
        <div v-if="purchaseValueLabel" class="flex flex-col gap-0.5">
          <dt class="text-hint">{{ t('gears.form.purchaseValue') }}</dt>
          <dd class="text-body">{{ purchaseValueLabel }}</dd>
        </div>
        <div v-if="totalCostLabel" class="flex flex-col gap-0.5">
          <dt class="text-hint">{{ t('gears.form.totalCost') }}</dt>
          <dd class="text-body">{{ totalCostLabel }}</dd>
        </div>
      </dl>
    </div>
    <div class="flex flex-col lg:flex-row gap-2 px-4 py-3">
      <Button size="sm" :aria-label="t('gears.actions.edit')" @click="emit('edit')">
        <Pencil class="size-4" aria-hidden="true" />
        {{ t('gears.actions.edit') }}
      </Button>
      <Button
        variant="destructive"
        size="sm"
        :aria-label="t('gears.actions.delete')"
        @click="emit('delete')"
      >
        <Trash2 class="size-4" aria-hidden="true" />
        {{ t('gears.actions.delete') }}
      </Button>
    </div>
  </Card>
</template>
