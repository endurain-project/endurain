<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { Activity, ActivityLap } from '@/features/activities/types'
import type { Units } from '@/features/activities/utils/format'

import { activityTypeIsSwimming, lapCyclesLabelKey } from '@/features/activities/utils/activityType'
import {
  combineMetric,
  formatDistance,
  formatElevation,
  formatHmsDuration,
} from '@/features/activities/utils/format'
import { normalizeLaps, summarizeActiveLaps } from '@/features/activities/utils/laps'
import { formatLapTempo } from '@/features/activities/utils/metrics'

const props = defineProps<{
  laps: ActivityLap[]
  activity: Activity
  units: Units
}>()

const { t } = useI18n()

const isSwimming = computed(() => activityTypeIsSwimming(props.activity.activityType))
// Swimming hides elevation and shows stroke rate in its place (v1 parity).
const showElevation = computed(() => !isSwimming.value)
const showStrokeRate = computed(() => isSwimming.value)
// FIT total_cycles means different things per sport (strokes, revolutions,
// strides, jumps); label the column accordingly.
const cyclesLabelKey = computed(() => lapCyclesLabelKey(props.activity.activityType))

const normalized = computed(() => normalizeLaps(props.laps, props.activity.activityType))
const hasIntensity = computed(() => normalized.value.some((entry) => entry.lap.intensity !== null))
// Any rest lap, whether flagged via FIT intensity or the swim heuristic. Swim
// rests carry no intensity field, so gating on hasIntensity alone would hide the
// active-total breakdown for swims — use this instead.
const hasRest = computed(() => normalized.value.some((entry) => entry.isRest))

// Active-only totals, shown only when the activity distinguishes rest laps
// (otherwise the header already covers the same numbers).
const activeSummary = computed(() => {
  if (!hasRest.value) {
    return null
  }
  const summary = summarizeActiveLaps(props.laps, props.activity.activityType)
  if (summary === null) {
    return null
  }
  return {
    distance: combineMetric(
      formatDistance(summary.totalDistance, props.activity.activityType, props.units),
    ),
    time: formatHmsDuration(summary.totalElapsedTime),
    tempo: formatLapTempo(
      summary.avgPace,
      summary.avgSpeed,
      props.activity.activityType,
      props.units,
    ),
  }
})

interface LapRow {
  id: number
  index: number
  intensity: string | null
  distance: string
  time: string
  tempo: string
  /** Relative-pace score (0–100), or `null` when the lap has no pace. */
  tempoScore: number | null
  elevation: string
  strokeRate: string
  cycles: string
  hr: string
  isRest: boolean
}

const rows = computed<LapRow[]>(() =>
  normalized.value.map((entry, index) => {
    const lap = entry.lap
    return {
      id: lap.id,
      index: index + 1,
      intensity: lap.intensity,
      distance: combineMetric(
        formatDistance(lap.totalDistance, props.activity.activityType, props.units),
      ),
      time: formatHmsDuration(lap.totalElapsedTime),
      // Rest laps record idle drift, so their pace is meaningless — blank it.
      tempo: entry.isRest
        ? '--'
        : formatLapTempo(
            lap.enhancedAvgPace,
            lap.enhancedAvgSpeed,
            props.activity.activityType,
            props.units,
          ),
      tempoScore: entry.isRest ? null : entry.normalizedScore,
      elevation:
        lap.totalAscent === null
          ? '--'
          : combineMetric(formatElevation(lap.totalAscent, props.units)),
      strokeRate: lap.avgCadence === null ? '--' : `${Math.round(lap.avgCadence)}`,
      cycles: lap.totalCycles === null ? '--' : `${lap.totalCycles}`,
      hr: lap.avgHeartRate === null ? '--' : `${Math.round(lap.avgHeartRate)} bpm`,
      isRest: entry.isRest,
    }
  }),
)
</script>

<template>
  <div>
    <p v-if="activeSummary" class="text-caption mb-2 text-muted-foreground">
      {{ t('activities.laps.activeSummary') }}:
      <span class="text-foreground">{{ activeSummary.distance }}</span>
      · <span class="text-foreground">{{ activeSummary.time }}</span> ·
      <span class="text-foreground">{{ activeSummary.tempo }}</span>
    </p>
    <div class="overflow-x-auto">
      <table class="w-full min-w-[28rem] border-collapse text-meta">
        <thead>
          <tr class="text-caption border-b border-border text-left">
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.lap') }}</th>
            <th v-if="hasIntensity" class="py-2 pe-3 font-medium">
              {{ t('activities.laps.intensity') }}
            </th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.distance') }}</th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.time') }}</th>
            <th class="py-2 pe-3 font-medium">{{ t('activities.laps.tempo') }}</th>
            <th v-if="showElevation" class="py-2 pe-3 font-medium">
              {{ t('activities.laps.elevation') }}
            </th>
            <th v-if="showStrokeRate" class="py-2 pe-3 font-medium">
              {{ t('activities.laps.strokeRate') }}
            </th>
            <th class="py-2 pe-3 font-medium">{{ t(cyclesLabelKey) }}</th>
            <th class="py-2 font-medium">{{ t('activities.laps.hr') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.id"
            class="border-b border-border/60 last:border-0"
            :class="row.isRest ? 'text-muted-foreground opacity-60' : ''"
          >
            <td class="py-2 pe-3 font-medium text-foreground">{{ row.index }}</td>
            <td v-if="hasIntensity" class="py-2 pe-3 capitalize text-muted-foreground">
              {{ row.intensity ?? '--' }}
            </td>
            <td class="py-2 pe-3 text-foreground">{{ row.distance }}</td>
            <td class="py-2 pe-3 text-foreground">{{ row.time }}</td>
            <td class="py-2 pe-3 text-foreground">
              <span>{{ row.tempo }}</span>
              <span
                v-if="row.tempoScore !== null"
                class="mt-1 block h-1 w-16 overflow-hidden rounded-full bg-muted"
                role="progressbar"
                :aria-valuenow="Math.round(row.tempoScore)"
                aria-valuemin="0"
                aria-valuemax="100"
              >
                <span
                  class="block h-full rounded-full bg-brand"
                  :style="{ width: `${row.tempoScore}%` }"
                />
              </span>
            </td>
            <td v-if="showElevation" class="py-2 pe-3 text-muted-foreground">
              {{ row.elevation }}
            </td>
            <td v-if="showStrokeRate" class="py-2 pe-3 text-muted-foreground">
              {{ row.strokeRate }}
            </td>
            <td class="py-2 pe-3 text-muted-foreground">{{ row.cycles }}</td>
            <td class="py-2 text-muted-foreground">{{ row.hr }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
