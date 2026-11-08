<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'
import { useUserDeletionQuery } from '@/features/users/composables/useUsers'

/**
 * Marks a user whose account deletion is queued, and follows the deletion so the
 * account leaves the users list and detail once it is erased.
 */
const props = defineProps<{
  /** The user queued for deletion. */
  userId: number
}>()

const { t } = useI18n()

useUserDeletionQuery(() => props.userId)
</script>

<template>
  <Badge variant="destructive">{{ t('settings.users.list.deleting') }}</Badge>
</template>
