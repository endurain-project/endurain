<script setup lang="ts">
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useToasts } from '@/composables/useToasts'
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

const { t } = useI18n()
const toasts = useToasts()
const deletions = useUserDeletionsStore()
const { data } = useUserDeletionQuery(() => props.jobId)

watch(data, (deletion) => {
  if (deletion && isTerminalJobState(deletion.status)) {
    if (deletion.status === 'failed') {
      toasts.error(t('settings.users.delete.failed'))
    }
    deletions.release(props.jobId)
  }
})
</script>

<template>
  <span hidden />
</template>
