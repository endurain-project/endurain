import type { ActivityExerciseTitle, ActivityWorkoutStep } from '@/features/activities/types'

/**
 * Expands `repeat_until_steps_cmplt` directives into concrete steps by repeating
 * the two preceding steps `targetValue - 1` times. Pure, so it is unit-testable.
 *
 * @param steps - The raw workout steps, in order.
 * @returns The expanded list of steps.
 */
export function expandWorkoutSteps(steps: ActivityWorkoutStep[]): ActivityWorkoutStep[] {
  const result: ActivityWorkoutStep[] = []
  steps.forEach((step, index) => {
    if (step.durationType === 'repeat_until_steps_cmplt') {
      const repeatCount = step.targetValue ?? 0
      const stepsToRepeat = steps.slice(Math.max(index - 2, 0), index)
      for (let i = 1; i < repeatCount; i += 1) {
        result.push(...stepsToRepeat)
      }
    } else {
      result.push(step)
    }
  })
  return result
}

/**
 * Resolves a human-readable exercise name from a FIT category/name code pair via
 * the exercise-title catalogue. Used by both steps
 * (exercise name/category) and sets (category subtype/category).
 *
 * @param titles - The exercise-title catalogue.
 * @param exerciseName - The FIT exercise-name code.
 * @param exerciseCategory - The FIT exercise-category code.
 * @returns The display name, or `null` when unknown.
 */
export function resolveExerciseName(
  titles: ActivityExerciseTitle[],
  exerciseName: number | null,
  exerciseCategory: number | null,
): string | null {
  if (exerciseName === null || exerciseCategory === null) {
    return null
  }
  const match = titles.find(
    (title) => title.exerciseName === exerciseName && title.exerciseCategory === exerciseCategory,
  )
  return match?.wktStepName ?? null
}
