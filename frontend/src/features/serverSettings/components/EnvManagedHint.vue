<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  /** The environment variable that sets the field; the hint renders only when given. */
  name?: string
}>()

const { t } = useI18n()
</script>

<template>
  <p v-if="name" class="text-hint">{{ t('settings.server.envLocked', { name }) }}</p>
</template>
