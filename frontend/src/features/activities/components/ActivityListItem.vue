<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { Activity } from '@/features/activities/types'
import type {
  ActivityMetricColumn,
  ActivityMetricKey,
} from '@/features/activities/utils/activityListColumns'
import type { FormattedMetric, Units } from '@/features/activities/utils/format'

import { NA_METRIC } from '@/features/activities/utils/activityListColumns'
import {
  activityTypeIsDistanceBased,
  activityTypeUsesPace,
  presentActivityType,
} from '@/features/activities/utils/activityType'
import {
  combineMetric,
  formatDistance,
  formatElevation,
  formatHmsDuration,
  formatPace,
  formatSpeed,
} from '@/features/activities/utils/format'

/**
 * One activity row in the activities list: a type icon, the linked name, the
 * start date and location, then the headline metrics in fixed columns
 * (distance, duration, pace/speed, elevation, plus an optional sort-only
 * calories/avg-HR column) that line up with the list's column header. Columns
 * that don't apply to a session (e.g. distance for a gym workout) render an em
 * dash so the remaining columns stay aligned. On mobile the columns collapse
 * into a single compact summary line.
 */
const props = defineProps<{
  /** The activity to render. */
  activity: Activity
  /** The viewer's unit system. */
  units: Units
  /** The columns to render, shared with the list header so they line up. */
  columns: readonly ActivityMetricColumn[]
}>()

const { locale } = useI18n()

const presentation = computed(() => presentActivityType(props.activity.activityType))
const isDistanceBased = computed(() => activityTypeIsDistanceBased(props.activity.activityType))
const usesPace = computed(() => activityTypeUsesPace(props.activity.activityType))

/** The localized start date, or `null` when the activity has no/invalid time. */
const dateLabel = computed(() => {
  if (!props.activity.startTime) {
    return null
  }
  const date = new Date(props.activity.startTime)
  if (Number.isNaN(date.getTime())) {
    return null
  }
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium' }).format(date)
})

/** "City, Country" (whichever parts are present), or `null`. */
const locationLabel = computed(() => {
  const place = props.activity.city ?? props.activity.town
  return [place, props.activity.country].filter(Boolean).join(', ') || null
})

const distanceMetric = computed(() =>
  formatDistance(props.activity.distance, props.activity.activityType, props.units),
)
const durationLabel = computed(() => formatHmsDuration(props.activity.totalTimerTime))
const tempoMetric = computed(() =>
  usesPace.value
    ? formatPace(props.activity.pace, props.activity.activityType, props.units)
    : formatSpeed(props.activity.averageSpeed, props.activity.activityType, props.units),
)
const elevationMetric = computed(() => formatElevation(props.activity.elevationGain, props.units))
const caloriesMetric = computed<FormattedMetric>(() => {
  const calories = props.activity.calories
  return calories !== null && calories !== undefined && Number.isFinite(calories)
    ? { value: String(Math.round(calories)), unit: 'kcal' }
    : NA_METRIC
})
const avgHrMetric = computed<FormattedMetric>(() => {
  const hr = props.activity.averageHr
  return hr !== null && hr !== undefined && Number.isFinite(hr)
    ? { value: String(Math.round(hr)), unit: 'bpm' }
    : NA_METRIC
})

/**
 * The formatted metric for each column, keyed for the template and the mobile
 * summary. Non-distance sessions show `NA_METRIC` for the distance, pace/speed,
 * and elevation columns so those columns read as an em dash. Calories and avg
 * HR apply regardless of whether the activity is distance-based.
 */
const cells = computed<Record<ActivityMetricKey, FormattedMetric>>(() => ({
  distance: isDistanceBased.value ? distanceMetric.value : NA_METRIC,
  duration: { value: durationLabel.value, unit: '' },
  paceSpeed: isDistanceBased.value ? tempoMetric.value : NA_METRIC,
  elevation: isDistanceBased.value ? elevationMetric.value : NA_METRIC,
  calories: caloriesMetric.value,
  avgHr: avgHrMetric.value,
}))

/** The compact "distance · duration · pace [· extra sort column]" line shown
 * only on mobile. The extra column (calories/avg HR) is appended when the
 * list is actively sorted by one of them, since it wouldn't otherwise appear
 * on narrow viewports. */
const mobileSummary = computed(() => {
  const parts: string[] = []
  if (cells.value.distance.value !== '--') {
    parts.push(combineMetric(cells.value.distance))
  }
  if (durationLabel.value !== '--') {
    parts.push(durationLabel.value)
  }
  if (cells.value.paceSpeed.value !== '--') {
    parts.push(combineMetric(cells.value.paceSpeed))
  }
  const extraColumn = props.columns.find((col) => col.key === 'calories' || col.key === 'avgHr')
  if (extraColumn && cells.value[extraColumn.key].value !== '--') {
    parts.push(combineMetric(cells.value[extraColumn.key]))
  }
  return parts.join(' · ')
})
</script>

<template>
  <div
    class="flex flex-col gap-1.5 px-4 py-3 transition-colors hover:bg-muted/50 sm:flex-row sm:items-center sm:gap-3"
  >
    <!-- Identity: type icon, linked name, date · location, mobile metric summary. -->
    <div class="flex min-w-0 items-center gap-3 sm:flex-1">
      <span
        class="flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
      >
        <component :is="presentation.icon" class="size-6" aria-hidden="true" />
      </span>
      <div class="min-w-0 flex-1">
        <RouterLink
          :to="{ name: 'activity', params: { id: activity.id } }"
          class="block truncate font-medium text-foreground hover:underline"
        >
          {{ activity.name }}
        </RouterLink>
        <p v-if="dateLabel || locationLabel" class="truncate text-hint">
          <span v-if="dateLabel">{{ dateLabel }}</span>
          <span v-if="dateLabel && locationLabel"> · </span>
          <span v-if="locationLabel">{{ locationLabel }}</span>
        </p>
        <p
          v-if="mobileSummary"
          class="mt-0.5 truncate text-meta tabular-nums text-foreground sm:hidden"
        >
          {{ mobileSummary }}
        </p>
      </div>
    </div>

    <!-- Headline metrics in fixed columns that align with the list header. -->
    <div class="hidden shrink-0 items-baseline gap-6 sm:flex">
      <div v-for="col in columns" :key="col.key" :class="['tabular-nums', col.cellClass]">
        <p
          v-if="cells[col.key].value !== '--'"
          class="text-metric font-medium leading-tight whitespace-nowrap text-foreground"
        >
          {{ cells[col.key].value }}
          <span v-if="cells[col.key].unit" class="text-hint font-normal">{{
            cells[col.key].unit
          }}</span>
        </p>
        <p v-else class="text-metric font-medium leading-tight text-muted-foreground">—</p>
      </div>
    </div>
  </div>
</template>
