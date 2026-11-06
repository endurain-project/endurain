import type { Schemas } from '@/types'

/** Where a background job is; every status read the backend answers for a job uses it. */
export type JobState = Schemas['JobState']

/** The states a job does not leave, so polling can stop. */
export const TERMINAL_JOB_STATES: readonly JobState[] = ['succeeded', 'failed']

/**
 * Whether a job has reached a state it will not leave.
 *
 * @param state - The job's `status`.
 * @returns `true` when the job succeeded or failed.
 */
export function isTerminalJobState(state: JobState): boolean {
  return TERMINAL_JOB_STATES.includes(state)
}
