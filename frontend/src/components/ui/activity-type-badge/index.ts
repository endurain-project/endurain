export { default as ActivityTypeBadge } from './ActivityTypeBadge.vue'

/** Activity categories that have a dedicated badge colour. */
export type ActivityBadgeType =
  'running' | 'cycling' | 'swimming' | 'hiking' | 'multisport' | 'other'

/**
 * Maps an activity category to its badge colour utilities. Full literal class
 * strings are required so Tailwind's scanner can see them (do not build these
 * names dynamically).
 */
export const activityBadgeClasses: Record<ActivityBadgeType, string> = {
  running: 'bg-activity-running-bg text-activity-running-text',
  cycling: 'bg-activity-cycling-bg text-activity-cycling-text',
  swimming: 'bg-activity-swimming-bg text-activity-swimming-text',
  hiking: 'bg-activity-hiking-bg text-activity-hiking-text',
  multisport: 'bg-activity-multisport-bg text-activity-multisport-text',
  other: 'bg-activity-other-bg text-activity-other-text',
}
