import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { GeoPoint } from '@/composables/useMapProvider'

import type { UnitKey } from '@/i18n'
import { themeColor } from '@/lib/themeColor'
import { formatFixed, formatNumber } from '@/utils/formatNumber'

import type {
  Activity,
  ActivityPrivacy,
  ActivityStreams,
  ActivityType,
  StreamChannel,
  StreamMetric,
} from '../types'
import {
  activityTypeIsRowing,
  activityTypeIsStandUpPaddling,
  activityTypeIsSwimming,
  activityTypeUsesPace,
} from './activityType'
import {
  cadenceUnitLabel,
  celsiusToFahrenheit,
  elevationToDisplay,
  formatElevation,
  formatHmsDuration,
  formatPace,
  formatPaceClock,
  formatSpeed,
  paceToDisplaySeconds,
  speedToDisplay,
  speedUnitLabel,
  type Units,
} from './format'
import { distinctElapsedTime } from './metrics'

/** The channel of {@link ActivityStreams} each chart metric plots. */
const METRIC_CHANNEL = {
  hr: 'heartRate',
  power: 'power',
  cadence: 'cadence',
  elevation: 'elevation',
  velocity: 'speed',
  pace: 'pace',
  temperature: 'temperature',
} as const satisfies Record<StreamMetric, keyof ActivityStreams>

/** Stable display order for the metric charts. */
export const STREAM_METRIC_ORDER: readonly StreamMetric[] = [
  'pace',
  'velocity',
  'cadence',
  'hr',
  'power',
  'elevation',
  'temperature',
]

/** i18n label key for each metric chart title. */
const METRIC_TITLE_KEY: Record<StreamMetric, string> = {
  hr: 'activities.streams.heartRate',
  power: 'activities.streams.power',
  cadence: 'activities.streams.cadence',
  elevation: 'activities.streams.elevation',
  velocity: 'activities.streams.speed',
  pace: 'activities.streams.pace',
  temperature: 'activities.streams.temperature',
}

/**
 * Series colour for each metric, read from the design tokens.
 */
const METRIC_COLOR: Record<StreamMetric, string> = {
  hr: themeColor('--color-hr'),
  power: themeColor('--color-effort'),
  cadence: themeColor('--color-cadence'),
  elevation: themeColor('--color-goal'),
  velocity: themeColor('--color-info'),
  pace: themeColor('--color-brand'),
  temperature: themeColor('--color-temperature'),
}

/**
 * Maps a metric to the privacy flag that hides it from non-owners, or `null`
 * when the metric has no privacy flag (temperature).
 */
export const METRIC_PRIVACY_FIELD: Record<StreamMetric, keyof ActivityPrivacy | null> = {
  hr: 'hideHr',
  power: 'hidePower',
  cadence: 'hideCadence',
  elevation: 'hideElevation',
  velocity: 'hideSpeed',
  pace: 'hidePace',
  temperature: null,
}

/**
 * Whether a metric is relevant to show for an activity type, following the
 * pace-vs-speed split: pace for foot/water sports, speed for cycling and other
 * speed sports, and no elevation for swimming. HR, power, cadence and
 * temperature are always relevant when present.
 *
 * @param metric - The stream metric.
 * @param activityType - Numeric activity type.
 * @returns Whether the metric should be shown for this activity type.
 */
export function isMetricRelevantForType(metric: StreamMetric, activityType: ActivityType): boolean {
  switch (metric) {
    case 'pace':
      return activityTypeUsesPace(activityType)
    case 'velocity':
      return !activityTypeUsesPace(activityType)
    case 'elevation':
      return !activityTypeIsSwimming(activityType)
    default:
      return true
  }
}

/**
 * Pace outlier threshold (in seconds for the display unit). Values slower than
 * this are dropped as GPS noise.
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The threshold in seconds, beyond which a pace sample is discarded.
 */
function paceThresholdSeconds(activityType: ActivityType, units: Units): number {
  if (activityTypeIsSwimming(activityType)) {
    // 10 min per 100m (metric) / per 100yd (imperial, ×1.0936).
    return units === 'imperial' ? 10 * 1.0936 * 60 : 10 * 60
  }
  if (activityTypeIsRowing(activityType) || activityTypeIsStandUpPaddling(activityType)) {
    return 10 * 60 // 10 min per 500m.
  }
  // 20 min per km (metric) / per mile (imperial, ×1.60934).
  return units === 'imperial' ? 20 * 1.60934 * 60 : 20 * 60
}

/** Reads a sample value, returning `NaN` for missing values. */
function num(value: number | null | undefined): number {
  return value === null || value === undefined || !Number.isFinite(value) ? Number.NaN : value
}

/**
 * Converts one sample of a metric's channel to its chart value. Returns `NaN` for missing or
 * filtered samples so the chart renders a gap.
 */
function extractValue(
  raw: number | null,
  metric: StreamMetric,
  activityType: ActivityType,
  units: Units,
): number {
  const value = num(raw)
  if (Number.isNaN(value)) {
    return Number.NaN
  }
  switch (metric) {
    case 'elevation':
      return elevationToDisplay(value, units)
    case 'velocity':
      return speedToDisplay(value, activityType, units)
    case 'pace': {
      const seconds = paceToDisplaySeconds(value, activityType, units)
      return seconds > paceThresholdSeconds(activityType, units) ? Number.NaN : seconds
    }
    case 'temperature':
      return units === 'imperial' ? celsiusToFahrenheit(value) : value
    default:
      return value
  }
}

/** Builds the per-metric value formatter used for chart ticks and tooltips. */
function valueFormatter(
  metric: StreamMetric,
  activityType: ActivityType,
  units: Units,
  unitLabel: (unit: UnitKey) => string,
): (value: number) => string {
  switch (metric) {
    case 'hr':
      return (v) => `${formatNumber(v)} ${unitLabel('bpm')}`
    case 'power':
      return (v) => `${formatNumber(v)} ${unitLabel('w')}`
    case 'cadence':
      return (v) => `${formatNumber(v)} ${unitLabel(cadenceUnitLabel(activityType))}`
    case 'elevation':
      return (v) => `${formatNumber(v)} ${unitLabel(units === 'imperial' ? 'ft' : 'm')}`
    case 'velocity':
      return (v) => `${formatFixed(v, 1)} ${unitLabel(speedUnitLabel(activityType, units))}`
    case 'pace':
      return (v) => formatPaceClock(v)
    case 'temperature':
      return (v) =>
        `${formatFixed(v, 1)} ${unitLabel(units === 'imperial' ? 'fahrenheit' : 'celsius')}`
    default:
      return (v) => String(v)
  }
}

/** Builds evenly-spaced distance labels (in km/mi) aligned to the sample count. */
function buildDistanceLabels(pointCount: number, totalMeters: number, units: Units): string[] {
  if (pointCount <= 0 || totalMeters <= 0) {
    return []
  }
  const totalDisplay = units === 'imperial' ? totalMeters / 1609.34 : totalMeters / 1000
  const labels: string[] = []
  for (let i = 0; i < pointCount; i += 1) {
    const fraction = pointCount === 1 ? 0 : i / (pointCount - 1)
    labels.push(formatFixed(totalDisplay * fraction, 1))
  }
  return labels
}

/** Builds time labels (H:MM:SS) from each sample's real offset from the activity start. */
function buildTimeLabels(offsetsMs: number[]): string[] {
  return offsetsMs.map((offset) => formatHmsDuration(Math.round(offset / 1000)))
}

/**
 * Builds the x-axis labels and their unit for a chart: distance (km/mi) when the
 * activity covers ground, otherwise each sample's time from the activity start
 * (strength/indoor sessions have no distance).
 *
 * @param offsetsMs - Each sample's time in milliseconds from the activity start.
 * @param activity - The activity (distance basis).
 * @param units - The user's unit system.
 * @returns One label per sample and their unit key (`null` for the self-describing time axis).
 */
function buildChartXAxis(
  offsetsMs: number[],
  activity: Activity,
  units: Units,
): { labels: string[]; unit: UnitKey | null } {
  if (activity.distance > 0) {
    return {
      labels: buildDistanceLabels(offsetsMs.length, activity.distance, units),
      unit: units === 'imperial' ? 'mi' : 'km',
    }
  }
  return { labels: buildTimeLabels(offsetsMs), unit: null }
}

/** A single stat shown beneath a stream chart (e.g. avg/max for that metric). */
export interface StreamStat {
  /** i18n label key. */
  labelKey: string
  /** Formatted value. */
  value: string
  /** Unit key, or `null` for a unitless value. */
  unit: UnitKey | null
}

/** Whether a numeric activity field is present and finite. */
function statPresent(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value)
}

/**
 * Builds the summary stats shown beneath a metric's chart, drawn from the
 * activity's aggregate fields (avg/max for the metric).
 *
 * @param metric - The chart metric.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @returns The ordered stats to render under the chart.
 */
function buildStreamStats(metric: StreamMetric, activity: Activity, units: Units): StreamStat[] {
  const type = activity.activityType
  const stats: StreamStat[] = []
  const push = (labelKey: string, formatted: { value: string; unit: UnitKey | null }): void => {
    stats.push({ labelKey, value: formatted.value, unit: formatted.unit })
  }
  const watts = (labelKey: string, value: number): void => {
    stats.push({ labelKey, value: formatNumber(value), unit: 'w' })
  }
  // The summary "Time" tile already shows the activity duration, so the speed
  // and pace rows add elapsed time only when stops make it longer.
  const pushElapsedTime = (): void => {
    const elapsed = distinctElapsedTime(activity)
    if (elapsed !== null) {
      stats.push({
        labelKey: 'activities.metrics.elapsedTime',
        value: formatHmsDuration(elapsed),
        unit: null,
      })
    }
  }

  switch (metric) {
    case 'hr':
      if (statPresent(activity.averageHr)) {
        stats.push({
          labelKey: 'activities.metrics.avgHr',
          value: formatNumber(activity.averageHr),
          unit: 'bpm',
        })
      }
      if (statPresent(activity.maxHr)) {
        stats.push({
          labelKey: 'activities.metrics.maxHr',
          value: formatNumber(activity.maxHr),
          unit: 'bpm',
        })
      }
      break
    case 'power':
      if (statPresent(activity.averagePower)) {
        watts('activities.metrics.avgPower', activity.averagePower)
      }
      if (statPresent(activity.maxPower)) {
        watts('activities.metrics.maxPower', activity.maxPower)
      }
      if (statPresent(activity.normalizedPower)) {
        watts('activities.metrics.normalizedPower', activity.normalizedPower)
      }
      break
    case 'cadence':
      if (statPresent(activity.averageCadence)) {
        stats.push({
          labelKey: 'activities.metrics.avgCadence',
          value: formatNumber(activity.averageCadence),
          unit: cadenceUnitLabel(type),
        })
      }
      if (statPresent(activity.maxCadence)) {
        stats.push({
          labelKey: 'activities.metrics.maxCadence',
          value: formatNumber(activity.maxCadence),
          unit: cadenceUnitLabel(type),
        })
      }
      break
    case 'elevation':
      if (statPresent(activity.elevationGain)) {
        push('activities.metrics.elevationGain', formatElevation(activity.elevationGain, units))
      }
      if (statPresent(activity.elevationLoss)) {
        push('activities.metrics.elevationLoss', formatElevation(activity.elevationLoss, units))
      }
      break
    case 'velocity':
      if (statPresent(activity.averageSpeed)) {
        push('activities.metrics.avgSpeed', formatSpeed(activity.averageSpeed, type, units))
      }
      if (statPresent(activity.maxSpeed)) {
        push('activities.metrics.maxSpeed', formatSpeed(activity.maxSpeed, type, units))
      }
      pushElapsedTime()
      break
    case 'pace':
      if (statPresent(activity.pace)) {
        push('activities.metrics.avgPace', formatPace(activity.pace, type, units))
      }
      pushElapsedTime()
      break
    case 'temperature':
      break
    default:
      break
  }
  return stats
}

/** A renderable metric chart derived from one stream. */
export interface StreamChart {
  /** The metric this chart plots. */
  metric: StreamMetric
  /** i18n key for the chart title. */
  titleKey: string
  /** Render options to hand to the chart provider. */
  render: ChartRenderOptions
  /** Summary stats shown beneath the chart. */
  stats: StreamStat[]
}

/**
 * Builds the chart of one metric from its channel, or `null` when the channel is missing or holds
 * no usable sample.
 *
 * @param streams - The activity's samples.
 * @param metric - The metric to plot.
 * @param activity - The activity domain model (type, distance, aggregate stats).
 * @param units - The user's unit system.
 * @param unitLabel - Resolves a unit key to its localized symbol for the chart ticks and tooltips.
 * @returns The chart model, or `null`.
 */
export function buildStreamChart(
  streams: ActivityStreams,
  metric: StreamMetric,
  activity: Activity,
  units: Units,
  unitLabel: (unit: UnitKey) => string,
): StreamChart | null {
  const channel: StreamChannel | null = streams[METRIC_CHANNEL[metric]]
  if (!channel) {
    return null
  }

  const type = activity.activityType
  const data = channel.map((value) => extractValue(value, metric, type, units))
  if (data.every((value) => Number.isNaN(value))) {
    return null
  }

  const xAxis = buildChartXAxis(streams.offsetsMs, activity, units)

  return {
    metric,
    titleKey: METRIC_TITLE_KEY[metric],
    render: {
      // All metric charts render as lines with a gradient fill for visual
      // consistency. Pace is plotted on a normal (non-inverted) axis like every
      // other metric; the y-tick/tooltip formatter renders it as M:SS.
      kind: 'line',
      series: [{ label: METRIC_TITLE_KEY[metric], data, color: METRIC_COLOR[metric] }],
      labels: xAxis.labels,
      xUnit: xAxis.unit ? unitLabel(xAxis.unit) : '',
      valueFormat: valueFormatter(metric, type, units, unitLabel),
      zoom: true,
    },
    stats: buildStreamStats(metric, activity, units),
  }
}

/**
 * Builds every metric chart for an activity, in display order and filtered by
 * (1) per-field privacy flags the viewer may see and (2) type relevance (pace
 * vs. speed, no elevation for swimming).
 *
 * @param streams - The activity's samples.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @param unitLabel - Resolves a unit key to its localized symbol for the chart ticks and tooltips.
 * @param isMetricVisible - Predicate deciding whether a metric is visible to
 *   the current viewer (owner vs. privacy flags).
 * @returns The ordered, visible, type-relevant chart models.
 */
export function buildStreamCharts(
  streams: ActivityStreams,
  activity: Activity,
  units: Units,
  unitLabel: (unit: UnitKey) => string,
  isMetricVisible: (metric: StreamMetric) => boolean,
): StreamChart[] {
  return STREAM_METRIC_ORDER.flatMap((metric) => {
    if (!isMetricVisible(metric) || !isMetricRelevantForType(metric, activity.activityType)) {
      return []
    }
    const chart = buildStreamChart(streams, metric, activity, units, unitLabel)
    return chart ? [chart] : []
  })
}

/**
 * Builds the GPS track polyline from the latitude and longitude channels, skipping samples
 * without a full position.
 *
 * @param streams - The activity's samples, or `null`/`undefined` while they are unavailable.
 * @returns Ordered geo points, or an empty array when no coordinates exist.
 */
export function extractTrackPoints(streams: ActivityStreams | null | undefined): GeoPoint[] {
  const { latitude, longitude } = streams ?? {}
  if (!latitude || !longitude) {
    return []
  }
  const points: GeoPoint[] = []
  latitude.forEach((lat, index) => {
    const lon = longitude[index]
    if (lat !== null && lon !== null && lon !== undefined) {
      // The map provider's GeoPoint uses `lng`; the backend names it `longitude`.
      points.push({ lat, lng: lon })
    }
  })
  return points
}
