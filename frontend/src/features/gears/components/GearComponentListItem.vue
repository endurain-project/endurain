<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Pencil, Trash2 } from '@lucide/vue'

import type { GearComponent } from '@/features/gears/types'
import type { Schemas } from '@/types'

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  currencySymbol,
  formatDuration,
  metersToDisplayDistance,
} from '@/features/gears/utils/format'
import {
  componentWearPercent,
  humanizeComponentType,
  isTimeBasedGear,
} from '@/features/gears/utils/gearComponentType'

const props = defineProps<{
  /** The component to render. */
  component: GearComponent
  /** The parent gear's numeric type, selecting distance- vs time-based wear. */
  gearType: number
  /** The viewer's measurement system. */
  units: Schemas['Units']
  /** The viewer's currency. */
  currency: Schemas['Currency']
}>()

const emit = defineEmits<{ edit: [component: GearComponent]; delete: [component: GearComponent] }>()

const { t, locale } = useI18n()

const title = computed(() => `${props.component.brand} ${props.component.model}`.trim())
const typeLabel = computed(() => humanizeComponentType(props.component.type))
const timeBased = computed(() => isTimeBasedGear(props.gearType))
const distanceUnit = computed(() =>
  props.units === 'imperial' ? t('gears.unitMi') : t('gears.unitKm'),
)

/** Accumulated usage, rendered as a duration (racquet) or distance + unit. */
const currentDisplay = computed(() =>
  timeBased.value
    ? formatDuration(props.component.currentTime)
    : `${metersToDisplayDistance(props.component.currentDistance, props.units)} ${distanceUnit.value}`,
)

const hasExpected = computed(
  () => props.component.expectedBaseUnits !== null && props.component.expectedBaseUnits > 0,
)

/** The wear threshold, rendered in the same unit as {@link currentDisplay}. */
const expectedDisplay = computed(() => {
  const base = props.component.expectedBaseUnits
  if (base === null) {
    return ''
  }
  return timeBased.value
    ? formatDuration(base)
    : `${metersToDisplayDistance(base, props.units)} ${distanceUnit.value}`
})

const usageText = computed(() =>
  hasExpected.value ? `${currentDisplay.value} / ${expectedDisplay.value}` : currentDisplay.value,
)

const wearPercent = computed(() =>
  componentWearPercent(
    timeBased.value ? props.component.currentTime : props.component.currentDistance,
    props.component.expectedBaseUnits,
  ),
)
const barWidth = computed(() => Math.min(100, Math.max(0, wearPercent.value ?? 0)))
// Flag a worn-out component (at or past its threshold) with the destructive hue.
const barClass = computed(() => ((wearPercent.value ?? 0) >= 100 ? 'bg-destructive' : 'bg-brand'))

/** Optional "Purchased {date} · {symbol}{value}" meta line. */
const metaLabel = computed(() => {
  const parts: string[] = []
  if (props.component.purchaseDate) {
    const date = new Date(props.component.purchaseDate)
    if (!Number.isNaN(date.getTime())) {
      const formatted = new Intl.DateTimeFormat(locale.value, {
        dateStyle: 'medium',
        timeZone: 'UTC',
      }).format(date)
      parts.push(t('gears.components.purchasedOn', { date: formatted }))
    }
  }
  if (props.component.purchaseValue !== null) {
    parts.push(`${currencySymbol(props.currency)}${props.component.purchaseValue}`)
  }
  return parts.join(' · ')
})
</script>

<template>
  <div class="px-4 py-3 space-y-1.5">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0 flex-1 space-y-1.5">
        <div class="flex items-center">
          <span class="truncate font-medium text-foreground">{{ title }}</span>
        </div>
        <div>
          <Badge v-if="!component.active" variant="destructive" class="self-start">
            {{ t('gears.components.inactive') }}
          </Badge>
        </div>
        <p class="truncate text-hint">{{ typeLabel }}</p>
      </div>

      <div class="flex shrink-0 items-center gap-1">
        <Button
          variant="ghost"
          size="icon-sm"
          :aria-label="t('gears.components.actions.edit')"
          @click="emit('edit', component)"
        >
          <Pencil class="size-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghostDestructive"
          size="icon-sm"
          :aria-label="t('gears.components.actions.delete')"
          @click="emit('delete', component)"
        >
          <Trash2 class="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>

    <div class="flex items-center justify-between gap-2 text-hint">
      <span class="truncate">{{ usageText }}</span>
      <span v-if="wearPercent !== null" class="shrink-0 tabular-nums">{{ wearPercent }}%</span>
    </div>
    <div
      v-if="hasExpected"
      class="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      :aria-valuenow="barWidth"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="t('gears.components.wearLabel', { name: title })"
    >
      <div class="h-full rounded-full" :class="barClass" :style="{ width: `${barWidth}%` }" />
    </div>

    <p v-if="metaLabel" class="text-hint">{{ metaLabel }}</p>
  </div>
</template>
