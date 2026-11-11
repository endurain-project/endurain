<script setup lang="ts">
import { watch } from 'vue'

import { useUserDeletionQuery } from '@/features/users/composables/useUsers'
import { useUserDeletionsStore } from '@/features/users/stores/userDeletions'
import { isTerminalJobState } from '@/services/jobStatus'

/**
 * Renders nothing; follows one queued account deletion until it ends, then stops tracking it.
 */
const props = defineProps<{
  /** The deletion job's id, from the 202 that queued it. */
  jobId: string
}>()

const deletions = useUserDeletionsStore()
const { data } = useUserDeletionQuery(() => props.jobId)

watch(data, (deletion) => {
  if (deletion && isTerminalJobState(deletion.status)) {
    deletions.release(props.jobId)
  }
})
</script>

<template>
  <span hidden />
</template>
