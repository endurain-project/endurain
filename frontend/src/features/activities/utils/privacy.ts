import type { ActivitySummary, ActivityPrivacy, StreamMetric } from '../types'
import type { MetricVisibility } from './metrics'
import { METRIC_PRIVACY_FIELD } from './streams'

/**
 * Whether the given viewer owns the activity. Owners bypass every per-field
 * privacy flag.
 *
 * @param activity - The activity.
 * @param currentUserId - The viewer's user id, or `null` when unauthenticated.
 * @returns Whether the viewer is the owner.
 */
export function isActivityOwner(activity: ActivitySummary, currentUserId: number | null): boolean {
  return currentUserId !== null && activity.userId === currentUserId
}

/**
 * Whether a privacy-gated field is visible to the viewer: always for the owner,
 * otherwise only when its hide flag is `false`.
 *
 * @param activity - The activity.
 * @param field - The privacy flag to evaluate.
 * @param currentUserId - The viewer's user id, or `null`.
 * @returns Whether the field is visible.
 */
export function canViewField(
  activity: ActivitySummary,
  field: keyof ActivityPrivacy,
  currentUserId: number | null,
): boolean {
  return isActivityOwner(activity, currentUserId) || !activity.privacy[field]
}

/**
 * Builds the privacy-gated visibility flags for the summary metrics.
 *
 * @param activity - The activity.
 * @param currentUserId - The viewer's user id, or `null`.
 * @returns Which metrics the viewer may see.
 */
export function buildMetricVisibility(
  activity: ActivitySummary,
  currentUserId: number | null,
): MetricVisibility {
  return {
    pace: canViewField(activity, 'hidePace', currentUserId),
    speed: canViewField(activity, 'hideSpeed', currentUserId),
    hr: canViewField(activity, 'hideHr', currentUserId),
    power: canViewField(activity, 'hidePower', currentUserId),
    cadence: canViewField(activity, 'hideCadence', currentUserId),
    elevation: canViewField(activity, 'hideElevation', currentUserId),
  }
}

/**
 * Builds a predicate deciding whether a stream metric chart is visible to the
 * viewer. Metrics without a privacy flag (temperature) are always visible.
 *
 * @param activity - The activity.
 * @param currentUserId - The viewer's user id, or `null`.
 * @returns A predicate over {@link StreamMetric}.
 */
export function streamMetricVisibility(
  activity: ActivitySummary,
  currentUserId: number | null,
): (metric: StreamMetric) => boolean {
  return (metric) => {
    const field = METRIC_PRIVACY_FIELD[metric]
    return field === null || canViewField(activity, field, currentUserId)
  }
}

/**
 * Whether any owner-only privacy flag is set, used to surface the "some details
 * are hidden from others" notice to the owner.
 *
 * @param activity - The activity.
 * @returns Whether at least one hide flag is enabled.
 */
export function hasHiddenFields(activity: ActivitySummary): boolean {
  return Object.values(activity.privacy).some(Boolean)
}
