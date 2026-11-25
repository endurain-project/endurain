import type { ActivitySummary, ActivityType } from '../types'

/**
 * One leg of a multisport activity as the switcher and the legs table name it.
 *
 * @property leg - The leg.
 * @property labelKey - i18n key of the leg's sport label.
 * @property number - The leg's place among the transitions when there are several, else `null`.
 */
export interface LegLabel {
  leg: ActivitySummary
  labelKey: string
  number: number | null
}

/** The activity type of a transition leg. */
const TRANSITION_TYPE: ActivityType = 'transition'

/**
 * Names each leg for its sport, numbering the transitions (first, second, ...) in leg order when
 * there are several, so "Transition 1" and "Transition 2" tell them apart.
 *
 * @param legs - The legs, in leg order.
 * @param labelKeyOf - Resolves the i18n label key of an activity type.
 * @returns One label per leg, in the same order.
 */
export function labelLegs(
  legs: readonly ActivitySummary[],
  labelKeyOf: (type: ActivityType) => string,
): LegLabel[] {
  const transitions = legs.filter((leg) => leg.activityType === TRANSITION_TYPE).length
  let seen = 0
  return legs.map((leg) => {
    const isNumbered = transitions > 1 && leg.activityType === TRANSITION_TYPE
    seen += isNumbered ? 1 : 0
    return { leg, labelKey: labelKeyOf(leg.activityType), number: isNumbered ? seen : null }
  })
}
