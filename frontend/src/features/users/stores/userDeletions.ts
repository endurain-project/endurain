import { ref } from 'vue'
import { defineStore } from 'pinia'

/** A deletion queued in this session: the user and the job that erases them. */
export interface TrackedDeletion {
  userId: number
  jobId: string
}

/**
 * The account deletions this administrator queued in this session and whose job is still followed.
 * Accounts already marked when the page loaded are not followed here.
 */
export const useUserDeletionsStore = defineStore('userDeletions', () => {
  const deletions = ref<TrackedDeletion[]>([])

  /** Starts following a deletion that was just queued, from the job the 202 returned. */
  function track(userId: number, jobId: string): void {
    if (!deletions.value.some((tracked) => tracked.jobId === jobId)) {
      deletions.value.push({ userId, jobId })
    }
  }

  /** Stops following a deletion job that reached a terminal state. */
  function release(jobId: string): void {
    deletions.value = deletions.value.filter((tracked) => tracked.jobId !== jobId)
  }

  return { deletions, track, release }
})
