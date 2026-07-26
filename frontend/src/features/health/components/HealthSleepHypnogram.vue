<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { SleepStage } from '@/features/health/types'

import { formatHoursMinutes } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The night's stage segments, in any order. */
  stages: SleepStage[]
  /**
   * Minutes to add to the GMT instants to get the sleeper's wall clock.
   *
   * Stage times are true UTC instants, so formatting them in the viewer's zone
   * would show a Tokyo night as an afternoon to a Lisbon viewer. The parent
   * derives this from the entry's recorded local/GMT pair; `0` falls back to
   * plain UTC labels.
   */
  offsetMinutes?: number
}>()

const { t, locale } = useI18n()

/**
 * Lanes top → bottom (Awake, REM, Light, Deep), mirroring the v1 hypnogram and
 * the convention of placing wakefulness at the top and deep sleep at the
 * bottom. `stageType` follows the backend enum (`0` deep … `3` awake).
 */
const LANES = [
  { stageType: 3, labelKey: 'awake', color: '#9ca3af' },
  { stageType: 2, labelKey: 'rem', color: '#60a5fa' },
  { stageType: 1, labelKey: 'light', color: '#2563eb' },
  { stageType: 0, labelKey: 'deep', color: '#1e40af' },
] as const

// SVG layout, in a fixed coordinate space scaled responsively by the viewBox.
const VIEW_W = 1000
const LANE_LABEL_W = 64
const RIGHT_PAD = 12
const TOP_PAD = 4
const LANE_H = 26
const LANE_GAP = 6
const AXIS_H = 20
const PLOT_LEFT = LANE_LABEL_W
const PLOT_RIGHT = VIEW_W - RIGHT_PAD
const PLOT_W = PLOT_RIGHT - PLOT_LEFT
const CHART_H = LANES.length * LANE_H + (LANES.length - 1) * LANE_GAP
const VIEW_H = TOP_PAD + CHART_H + AXIS_H
const TICK_COUNT = 5

/** Parses an ISO timestamp to epoch ms, or `null` when missing/invalid. */
function toMs(value: string | null): number | null {
  if (!value) return null
  const ms = new Date(value).getTime()
  return Number.isNaN(ms) ? null : ms
}

/** The y offset of a lane (0 = top) in the SVG coordinate space. */
function laneY(laneIndex: number): number {
  return TOP_PAD + laneIndex * (LANE_H + LANE_GAP)
}

/** Stage segments that carry a valid, positive-length time span. */
const prepared = computed(() =>
  props.stages
    .map((stage) => {
      const startMs = toMs(stage.startTimeGmt)
      const endMs = toMs(stage.endTimeGmt)
      const lane = LANES.find((entry) => entry.stageType === stage.stageType) ?? null
      return { stage, startMs, endMs, lane }
    })
    .filter(
      (
        item,
      ): item is typeof item & {
        startMs: number
        endMs: number
        lane: (typeof LANES)[number]
      } =>
        item.lane !== null &&
        item.startMs !== null &&
        item.endMs !== null &&
        item.endMs > item.startMs,
    ),
)

/** Whether there is at least one plottable segment. */
const hasSegments = computed(() => prepared.value.length > 0)

/** The overall [start, end] window across all segments. */
const domain = computed(() => {
  const starts = prepared.value.map((item) => item.startMs)
  const ends = prepared.value.map((item) => item.endMs)
  return { start: Math.min(...starts), end: Math.max(...ends) }
})

/** Maps an epoch ms onto the plot's x axis. */
function xFor(ms: number): number {
  const { start, end } = domain.value
  const span = end - start
  const frac = span > 0 ? (ms - start) / span : 0
  return PLOT_LEFT + frac * PLOT_W
}

/** Formats an epoch ms as a locale-aware `HH:mm` clock label in the sleeper's zone. */
const clockLabel = computed(() => {
  const formatter = new Intl.DateTimeFormat(locale.value, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    // Shift the instant by the recording offset and read it back in UTC, so the
    // label is the wall clock the sleeper saw rather than the viewer's.
    timeZone: 'UTC',
  })
  const offsetMs = (props.offsetMinutes ?? 0) * 60000
  return (ms: number) => formatter.format(new Date(ms + offsetMs))
})

/** The drawable rectangles, one per stage segment. */
const segments = computed(() =>
  prepared.value.map((item, index) => {
    const x = xFor(item.startMs)
    const width = Math.max(2, xFor(item.endMs) - x)
    const laneIndex = LANES.indexOf(item.lane)
    const durationSeconds =
      item.stage.durationSeconds ?? Math.round((item.endMs - item.startMs) / 1000)
    return {
      key: `${index}-${item.startMs}`,
      x,
      width,
      y: laneY(laneIndex),
      color: item.lane.color,
      label: t(`health.sleep.hypnogram.${item.lane.labelKey}`),
      startLabel: clockLabel.value(item.startMs),
      endLabel: clockLabel.value(item.endMs),
      durationLabel: formatHoursMinutes(durationSeconds),
    }
  }),
)

/** Evenly spaced time-axis ticks across the sleep window. */
const ticks = computed(() => {
  const { start, end } = domain.value
  if (end <= start) {
    return [{ key: 'single', x: xFor(start), label: clockLabel.value(start) }]
  }
  return Array.from({ length: TICK_COUNT }, (_, index) => {
    const ms = start + ((end - start) * index) / (TICK_COUNT - 1)
    return { key: String(index), x: xFor(ms), label: clockLabel.value(ms) }
  })
})

/** Lane rows with their resolved label and centre y for rendering. */
const laneRows = computed(() =>
  LANES.map((lane, index) => ({
    key: lane.labelKey,
    label: t(`health.sleep.hypnogram.${lane.labelKey}`),
    color: lane.color,
    centerY: laneY(index) + LANE_H / 2,
  })),
)
</script>

<template>
  <figure class="m-0 flex min-w-0 flex-col gap-2">
    <figcaption class="text-caption">{{ t('health.sleep.hypnogram.title') }}</figcaption>
    <p v-if="!hasSegments" class="text-hint">{{ t('health.sleep.hypnogram.noData') }}</p>
    <svg
      v-else
      :viewBox="`0 0 ${VIEW_W} ${VIEW_H}`"
      class="block h-auto w-full max-w-full"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      :aria-label="t('health.sleep.hypnogram.title')"
    >
      <!-- Lane guides and left-hand labels. -->
      <g v-for="lane in laneRows" :key="lane.key">
        <text
          :x="PLOT_LEFT - 8"
          :y="lane.centerY"
          text-anchor="end"
          dominant-baseline="middle"
          class="fill-muted-foreground text-micro"
        >
          {{ lane.label }}
        </text>
      </g>
      <!-- Time-axis gridlines and labels. -->
      <g v-for="tick in ticks" :key="tick.key">
        <line
          :x1="tick.x"
          :y1="TOP_PAD"
          :x2="tick.x"
          :y2="TOP_PAD + CHART_H"
          class="stroke-border"
          stroke-width="1"
          stroke-dasharray="2 3"
        />
        <text
          :x="tick.x"
          :y="VIEW_H - 6"
          text-anchor="middle"
          class="fill-muted-foreground text-micro"
        >
          {{ tick.label }}
        </text>
      </g>
      <!-- Stage segments. -->
      <rect
        v-for="segment in segments"
        :key="segment.key"
        :x="segment.x"
        :y="segment.y"
        :width="segment.width"
        :height="LANE_H"
        :fill="segment.color"
        rx="2"
      >
        <title>
          {{ segment.label }} · {{ segment.startLabel }}–{{ segment.endLabel }} ·
          {{ segment.durationLabel }}
        </title>
      </rect>
    </svg>
  </figure>
</template>
