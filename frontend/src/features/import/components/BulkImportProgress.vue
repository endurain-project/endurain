<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { type ActivityIngestionJob, isTerminalIngestionJob } from '@/features/upload/types'

const props = defineProps<{ job: ActivityIngestionJob }>()

const { t } = useI18n()

const total = computed(() => props.job.files_total ?? 0)
const done = computed(() => props.job.files_done ?? 0)
const failed = computed(() => props.job.files_failed ?? 0)
const finished = computed(() => isTerminalIngestionJob(props.job))
const stagingFailed = computed(() => props.job.status === 'failed')
</script>

<template>
  <p class="text-hint" role="status" aria-live="polite">
    <template v-if="stagingFailed">{{ t('settings.import.job.failed') }}</template>
    <template v-else-if="finished">
      {{ t('settings.import.job.finished', { done, failed, total }) }}
    </template>
    <template v-else-if="total === 0">{{ t('settings.import.job.preparing') }}</template>
    <template v-else>{{ t('settings.import.job.progress', { done, failed, total }) }}</template>
  </p>
</template>
