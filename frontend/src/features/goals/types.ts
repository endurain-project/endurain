import type { Schemas } from '@/types'

/** Raw goal payload (snake_case wire shape). */
export type GoalDto = Schemas['UsersGoalRead']

/** Create body for a new goal (the matching goal value is required). */
export type GoalCreateDto = Schemas['UsersGoalCreate']

/** Update body for a goal (includes `id` and `user_id`). */
export type GoalUpdateDto = Schemas['UsersGoalUpdate']

/** Raw goal-progress payload (snake_case wire shape) for a single interval. */
export type GoalProgressDto = Schemas['UsersGoalProgress']

/** A goal's recurrence interval. */
export type GoalInterval = Schemas['UsersGoalCreate']['interval']

/** The activity type a goal targets. */
export type GoalActivityType = Schemas['UsersGoalCreate']['activity_type']

/** The metric a goal measures. */
export type GoalMetric = Schemas['UsersGoalCreate']['goal_type']

/**
 * The clean, camel-cased goal model used across the goals zone. Mapped from
 * {@link GoalDto} at the service boundary so components never touch the raw DTO.
 * Exactly one of the target fields is set — the one matching {@link goalType} —
 * mirroring the backend's "one value per goal type" invariant.
 *
 * @property id - Stable unique identifier.
 * @property userId - Owner's user id (round-tripped on update).
 * @property interval - Recurrence window the goal is measured over.
 * @property activityType - The activity the goal applies to.
 * @property goalType - The metric being targeted.
 * @property calories - Target calories (kcal) when `goalType` is `calories`, else `null`.
 * @property activitiesNumber - Target activity count when `goalType` is `activities`, else `null`.
 * @property distanceMeters - Target distance in metres when `goalType` is `distance`, else `null`.
 * @property elevationMeters - Target elevation gain in metres when `goalType` is `elevation`, else `null`.
 * @property durationSeconds - Target duration in seconds when `goalType` is `duration`, else `null`.
 */
export interface Goal {
  id: number
  userId: number
  /** The row version, sent back in `If-Match` so an edit of a stale copy is refused. */
  version: number
  interval: GoalInterval
  activityType: GoalActivityType
  goalType: GoalMetric
  calories: number | null
  activitiesNumber: number | null
  distanceMeters: number | null
  elevationMeters: number | null
  durationSeconds: number | null
}

/**
 * The editable goal fields shared by create and update. The service builds the
 * wire body from this; only the target matching {@link goalType} is expected to
 * be non-null (the backend rejects a mismatched or missing target).
 */
export interface GoalInput {
  interval: GoalInterval
  activityType: GoalActivityType
  goalType: GoalMetric
  calories: number | null
  activitiesNumber: number | null
  distanceMeters: number | null
  elevationMeters: number | null
  durationSeconds: number | null
}

/**
 * The active goal-list filters. Each is `null` when not constraining the list,
 * mirroring the backend's optional `interval` / `activity_type` / `goal_type`
 * query parameters.
 */
export interface GoalFilters {
  interval: GoalInterval | null
  activityType: GoalActivityType | null
  goalType: GoalMetric | null
}

/**
 * A goal's progress for the current interval, as shown on the home dashboard.
 * Mapped from {@link GoalProgressDto} at the service boundary. `total` is the
 * achieved value and `target` the goal value for the active {@link goalType};
 * both are expressed in the metric's base unit (metres, seconds, kcal, count).
 *
 * @property goalId - The owning goal's id.
 * @property interval - The recurrence window this progress covers.
 * @property activityType - The activity the goal applies to.
 * @property goalType - The metric being targeted.
 * @property percentageCompleted - Completion percentage (0–100+), `0` when unknown.
 * @property total - Achieved value in the metric's base unit, `0` when unknown.
 * @property target - Target value in the metric's base unit, `null` when unset.
 */
export interface GoalProgress {
  goalId: number
  interval: GoalInterval
  activityType: GoalActivityType
  goalType: GoalMetric
  percentageCompleted: number
  total: number
  target: number | null
}
