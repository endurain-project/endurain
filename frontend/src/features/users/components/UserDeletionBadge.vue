<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'

/** Marks a user whose account deletion is queued. */
const { t } = useI18n()
</script>

<template>
  <Badge variant="destructive">{{ t('settings.users.list.deleting') }}</Badge>
</template>
