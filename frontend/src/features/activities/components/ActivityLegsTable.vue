<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { ActivitySummary } from '@/features/activities/types'
import type { FormattedMetric, Units } from '@/features/activities/utils/format'

import { useUnitFormat } from '@/composables/useUnitFormat'
import {
  activityTypeIsDistanceBased,
  activityTypeUsesPace,
  presentActivityType,
} from '@/features/activities/utils/activityType'
import {
  formatDistance,
  formatHmsDuration,
  formatPace,
  formatSpeed,
} from '@/features/activities/utils/format'
import { activityDuration } from '@/features/activities/utils/metrics'
import { buildMetricVisibility } from '@/features/activities/utils/privacy'
import { formatNumber } from '@/utils/formatNumber'

const props = defineProps<{
  /** The legs, in leg order. */
  legs: ActivitySummary[]
  units: Units
  /** The viewer's user id, or `null` when unauthenticated. */
  currentUserId: string | null
}>()

const { t } = useI18n()
const { unitLabel, formatMetric } = useUnitFormat()

/** Renders a metric as `value unit`, or `--` when the leg has no reading. */
function metricLabel(metric: FormattedMetric | null): string {
  return metric === null || metric.value === '--' ? '--' : formatMetric(metric)
}

const rows = computed(() =>
  props.legs.map((leg) => {
    const visibility = buildMetricVisibility(leg, props.currentUserId)
    const type = leg.activityType
    const tempo = activityTypeUsesPace(type)
      ? visibility.pace && formatPace(leg.pace, type, props.units)
      : visibility.speed && formatSpeed(leg.averageSpeed, type, props.units)
    const duration = activityDuration(leg)
    return {
      id: leg.id,
      name: leg.name,
      icon: presentActivityType(type).icon,
      typeLabelKey: presentActivityType(type).labelKey,
      time: duration === null ? '--' : formatHmsDuration(duration),
      distance: activityTypeIsDistanceBased(type)
        ? metricLabel(formatDistance(leg.distance, type, props.units))
        : '--',
      tempo: metricLabel(tempo || null),
      hr:
        visibility.hr && leg.averageHr !== null
          ? `${formatNumber(leg.averageHr)} ${unitLabel('bpm')}`
          : '--',
    }
  }),
)
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full min-w-[28rem] border-collapse text-meta">
      <thead>
        <tr class="text-caption border-b border-border text-left">
          <th class="py-2 pe-3 font-medium">{{ t('activities.multisport.leg') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.time') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.distance') }}</th>
          <th class="py-2 pe-3 font-medium">{{ t('activities.laps.tempo') }}</th>
          <th class="py-2 font-medium">{{ t('activities.laps.hr') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.id" class="border-b border-border/60 last:border-0">
          <td class="py-2 pe-3">
            <RouterLink
              :to="{ name: 'activity', params: { id: row.id } }"
              class="flex items-center gap-2 font-medium text-foreground hover:underline"
            >
              <component
                :is="row.icon"
                class="size-4 shrink-0 text-muted-foreground"
                :aria-label="t(row.typeLabelKey)"
                role="img"
              />
              <span class="truncate">{{ row.name }}</span>
            </RouterLink>
          </td>
          <td class="py-2 pe-3 text-foreground">{{ row.time }}</td>
          <td class="py-2 pe-3 text-foreground">{{ row.distance }}</td>
          <td class="py-2 pe-3 text-foreground">{{ row.tempo }}</td>
          <td class="py-2 text-muted-foreground">{{ row.hr }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
