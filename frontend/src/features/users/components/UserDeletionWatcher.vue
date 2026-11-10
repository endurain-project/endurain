<script setup lang="ts">
import { watch } from 'vue'

import { useUserDeletionQuery } from '@/features/users/composables/useUsers'
import { useUserDeletionsStore } from '@/features/users/stores/userDeletions'
import { isTerminalJobState } from '@/services/jobStatus'

/**
 * Renders nothing; follows one user's queued deletion until it ends, then stops tracking it.
 */
const props = defineProps<{
  /** The user queued for deletion. */
  userId: number
}>()

const deletions = useUserDeletionsStore()
const { data } = useUserDeletionQuery(() => props.userId)

watch(data, (deletion) => {
  if (deletion && isTerminalJobState(deletion.status)) {
    deletions.release(props.userId)
  }
})
</script>

<template>
  <span hidden />
</template>
