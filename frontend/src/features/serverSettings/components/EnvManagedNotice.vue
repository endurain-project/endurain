<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { Alert } from '@/components/ui/alert'

defineProps<{
  /** The environment variables that lock fields in the section; the notice renders only when any. */
  names: string[]
}>()

const { t } = useI18n()
</script>

<template>
  <Alert v-if="names.length > 0" kind="info">
    {{ t('settings.server.envSection', { names: names.join(', ') }) }}
  </Alert>
</template>
