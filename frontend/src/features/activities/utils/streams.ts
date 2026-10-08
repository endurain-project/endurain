import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { GeoPoint } from '@/composables/useMapProvider'

import { themeColor } from '@/lib/themeColor'

import type {
  Activity,
  ActivityPrivacy,
  ActivityStream,
  StreamMetric,
  StreamWaypoint,
} from '../types'
import { STREAM_TYPE } from '../types'
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

/** Maps a numeric stream type to its metric kind. */
const METRIC_BY_TYPE: Record<number, StreamMetric> = {
  [STREAM_TYPE.hr]: 'hr',
  [STREAM_TYPE.power]: 'power',
  [STREAM_TYPE.cadence]: 'cadence',
  [STREAM_TYPE.elevation]: 'elevation',
  [STREAM_TYPE.velocity]: 'velocity',
  [STREAM_TYPE.pace]: 'pace',
  [STREAM_TYPE.temperature]: 'temperature',
}

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
 * Series colour for each metric. Five map directly to the design-system
 * semantic tokens; cadence and temperature have no semantic token, so they use
 * the conventional fitness-chart colours (violet / orange) that read distinctly
 * against the others.
 */
const METRIC_COLOR: Record<StreamMetric, string> = {
  hr: themeColor('--color-hr'),
  power: themeColor('--color-effort'),
  cadence: '#a855f7', // no token — conventional cadence violet
  elevation: themeColor('--color-goal'),
  velocity: themeColor('--color-info'),
  pace: themeColor('--color-brand'),
  temperature: '#f97316', // no token — conventional temperature orange
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
 * Whether a metric is relevant to show for an activity type, mirroring v1's
 * pace-vs-speed split: pace for foot/water sports, speed for cycling and other
 * speed sports, and no elevation for swimming. HR, power, cadence and
 * temperature are always relevant when present.
 *
 * @param metric - The stream metric.
 * @param activityType - Numeric activity type.
 * @returns Whether the metric should be shown for this activity type.
 */
export function isMetricRelevantForType(metric: StreamMetric, activityType: number): boolean {
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
 * this are dropped as GPS noise, mirroring v1.
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The threshold in seconds, beyond which a pace sample is discarded.
 */
function paceThresholdSeconds(activityType: number, units: Units): number {
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

/** Reads a numeric waypoint field, returning `NaN` for missing values. */
function num(value: number | null | undefined): number {
  return value === null || value === undefined || !Number.isFinite(value) ? Number.NaN : value
}

/**
 * Extracts the converted chart value for a single waypoint and metric. Returns
 * `NaN` for missing or filtered samples so the chart renders a gap.
 */
function extractValue(
  waypoint: StreamWaypoint,
  metric: StreamMetric,
  activityType: number,
  units: Units,
): number {
  switch (metric) {
    case 'hr':
      return num(waypoint.hr)
    case 'power':
      return num(waypoint.power)
    case 'cadence': {
      const cad = num(waypoint.cad)
      return Number.isNaN(cad) ? Number.NaN : cad
    }
    case 'elevation': {
      const ele = num(waypoint.ele)
      return Number.isNaN(ele) ? Number.NaN : elevationToDisplay(ele, units)
    }
    case 'velocity': {
      const vel = num(waypoint.vel)
      return Number.isNaN(vel) ? Number.NaN : speedToDisplay(vel, activityType, units)
    }
    case 'pace': {
      const pace = num(waypoint.pace)
      if (Number.isNaN(pace) || pace <= 0) {
        return Number.NaN
      }
      const seconds = paceToDisplaySeconds(pace, activityType, units)
      return seconds > paceThresholdSeconds(activityType, units) ? Number.NaN : seconds
    }
    case 'temperature': {
      const temp = num(waypoint.temp)
      return Number.isNaN(temp)
        ? Number.NaN
        : units === 'imperial'
          ? celsiusToFahrenheit(temp)
          : temp
    }
    default:
      return Number.NaN
  }
}

/** Builds the per-metric value formatter used for chart ticks and tooltips. */
function valueFormatter(
  metric: StreamMetric,
  activityType: number,
  units: Units,
): (value: number) => string {
  switch (metric) {
    case 'hr':
      return (v) => `${Math.round(v)} bpm`
    case 'power':
      return (v) => `${Math.round(v)} W`
    case 'cadence':
      return (v) => `${Math.round(v)} ${cadenceUnitLabel(activityType)}`
    case 'elevation':
      return (v) => `${Math.round(v)} ${units === 'imperial' ? 'ft' : 'm'}`
    case 'velocity':
      return (v) => `${v.toFixed(1)} ${speedUnitLabel(activityType, units)}`
    case 'pace':
      return (v) => formatPaceClock(v)
    case 'temperature':
      return (v) => `${v.toFixed(1)}°${units === 'imperial' ? 'F' : 'C'}`
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
    labels.push((totalDisplay * fraction).toFixed(1))
  }
  return labels
}

/** Builds evenly-spaced elapsed-time labels (H:MM:SS) aligned to the sample count. */
function buildTimeLabels(pointCount: number, totalSeconds: number): string[] {
  if (pointCount <= 0 || totalSeconds <= 0) {
    return []
  }
  const labels: string[] = []
  for (let i = 0; i < pointCount; i += 1) {
    const fraction = pointCount === 1 ? 0 : i / (pointCount - 1)
    labels.push(formatHmsDuration(Math.round(totalSeconds * fraction)))
  }
  return labels
}

/**
 * Builds the x-axis labels and their unit for a chart: distance (km/mi) when the
 * activity covers ground, otherwise elapsed time (strength/indoor sessions have
 * no distance), falling back to sample indices so a line always renders. An
 * empty label array leaves the category axis with no slots, so the line would
 * not draw at all — this is why strength activities showed an empty HR chart.
 *
 * @param pointCount - Number of samples in the series.
 * @param activity - The activity (distance / time basis).
 * @param units - The user's unit system.
 * @returns Labels of length `pointCount` and their unit suffix (`''` for
 *   self-describing axes such as time, or the index fallback).
 */
function buildChartXAxis(
  pointCount: number,
  activity: Activity,
  units: Units,
): { labels: string[]; unit: string } {
  if (activity.distance > 0) {
    return {
      labels: buildDistanceLabels(pointCount, activity.distance, units),
      unit: units === 'imperial' ? 'mi' : 'km',
    }
  }
  const seconds = activity.totalElapsedTime ?? activity.totalTimerTime ?? 0
  if (seconds > 0) {
    return { labels: buildTimeLabels(pointCount, seconds), unit: '' }
  }
  const labels: string[] = []
  for (let i = 0; i < pointCount; i += 1) {
    labels.push(String(i + 1))
  }
  return { labels, unit: '' }
}

/** A single stat shown beneath a stream chart (e.g. avg/max for that metric). */
export interface StreamStat {
  /** i18n label key. */
  labelKey: string
  /** Formatted value. */
  value: string
  /** Unit suffix (may be empty). */
  unit: string
}

/** Whether a numeric activity field is present and finite. */
function statPresent(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value)
}

/**
 * Builds the summary stats shown beneath a metric's chart, drawn from the
 * activity's aggregate fields (avg/max for the metric), mirroring v1's per-chart
 * stat rows.
 *
 * @param metric - The chart metric.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @returns The ordered stats to render under the chart.
 */
function buildStreamStats(metric: StreamMetric, activity: Activity, units: Units): StreamStat[] {
  const type = activity.activityType
  const stats: StreamStat[] = []
  const push = (labelKey: string, formatted: { value: string; unit: string }): void => {
    stats.push({ labelKey, value: formatted.value, unit: formatted.unit })
  }
  const watts = (labelKey: string, value: number): void => {
    stats.push({ labelKey, value: String(Math.round(value)), unit: 'W' })
  }

  switch (metric) {
    case 'hr':
      if (statPresent(activity.averageHr)) {
        stats.push({
          labelKey: 'activities.metrics.avgHr',
          value: String(Math.round(activity.averageHr)),
          unit: 'bpm',
        })
      }
      if (statPresent(activity.maxHr)) {
        stats.push({
          labelKey: 'activities.metrics.maxHr',
          value: String(Math.round(activity.maxHr)),
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
          value: String(Math.round(activity.averageCadence)),
          unit: cadenceUnitLabel(type),
        })
      }
      if (statPresent(activity.maxCadence)) {
        stats.push({
          labelKey: 'activities.metrics.maxCadence',
          value: String(Math.round(activity.maxCadence)),
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
      break
    case 'pace':
      if (statPresent(activity.pace)) {
        push('activities.metrics.avgPace', formatPace(activity.pace, type, units))
      }
      if (statPresent(activity.totalTimerTime)) {
        stats.push({
          labelKey: 'activities.metrics.movingTime',
          value: formatHmsDuration(activity.totalTimerTime),
          unit: '',
        })
      }
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
 * Builds a renderable chart from a single stream, or `null` when the stream
 * type is unknown or carries no usable samples.
 *
 * @param stream - The metric stream.
 * @param activity - The activity domain model (type, distance, aggregate stats).
 * @param units - The user's unit system.
 * @returns The chart model, or `null`.
 */
export function buildStreamChart(
  stream: ActivityStream,
  activity: Activity,
  units: Units,
): StreamChart | null {
  const metric = METRIC_BY_TYPE[stream.streamType]
  if (!metric || stream.waypoints.length === 0) {
    return null
  }

  const type = activity.activityType
  const data = stream.waypoints.map((waypoint) => extractValue(waypoint, metric, type, units))
  if (data.every((value) => Number.isNaN(value))) {
    return null
  }

  const xAxis = buildChartXAxis(data.length, activity, units)

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
      xUnit: xAxis.unit,
      valueFormat: valueFormatter(metric, type, units),
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
 * @param streams - The activity's metric streams.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @param isMetricVisible - Predicate deciding whether a metric is visible to
 *   the current viewer (owner vs. privacy flags).
 * @returns The ordered, visible, type-relevant chart models.
 */
export function buildStreamCharts(
  streams: ActivityStream[],
  activity: Activity,
  units: Units,
  isMetricVisible: (metric: StreamMetric) => boolean,
): StreamChart[] {
  const type = activity.activityType
  const byMetric = new Map<StreamMetric, StreamChart>()
  for (const stream of streams) {
    const metric = METRIC_BY_TYPE[stream.streamType]
    if (
      !metric ||
      byMetric.has(metric) ||
      !isMetricVisible(metric) ||
      !isMetricRelevantForType(metric, type)
    ) {
      continue
    }
    const chart = buildStreamChart(stream, activity, units)
    if (chart) {
      byMetric.set(metric, chart)
    }
  }
  return STREAM_METRIC_ORDER.flatMap((metric) => {
    const chart = byMetric.get(metric)
    return chart ? [chart] : []
  })
}

/**
 * Extracts the GPS track polyline from whichever stream carries coordinates.
 *
 * @param streams - The activity's metric streams.
 * @returns Ordered geo points, or an empty array when no coordinates exist.
 */
export function extractTrackPoints(streams: ActivityStream[]): GeoPoint[] {
  for (const stream of streams) {
    const points: GeoPoint[] = []
    for (const waypoint of stream.waypoints) {
      const lat = num(waypoint.lat)
      const lon = num(waypoint.lon)
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
        // The map provider's GeoPoint uses `lng`; the backend stores `lon`.
        points.push({ lat, lng: lon })
      }
    }
    if (points.length > 0) {
      return points
    }
  }
  return []
}
