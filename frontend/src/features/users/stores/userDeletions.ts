import { ref } from 'vue'
import { defineStore } from 'pinia'

/**
 * The accounts this administrator queued for deletion in this session and whose progress is still
 * followed. Accounts already marked when the page loaded are not followed.
 */
export const useUserDeletionsStore = defineStore('userDeletions', () => {
  const userIds = ref<number[]>([])

  /** Starts following a deletion that was just queued. */
  function track(id: number): void {
    if (!userIds.value.includes(id)) {
      userIds.value.push(id)
    }
  }

  /** Stops following a deletion that reached a terminal state. */
  function release(id: number): void {
    userIds.value = userIds.value.filter((tracked) => tracked !== id)
  }

  return { userIds, track, release }
})
