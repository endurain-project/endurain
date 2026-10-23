<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { RestingHeartRateEntry } from '@/features/health/types'

import { INTEGRATION_LOGOS } from '@/constants/integrationLogos'
import { formatHealthEntryDate, formatRestingHeartRate } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** The resting-heart-rate entry to render. */
  entry: RestingHeartRateEntry
}>()

const { t, locale } = useI18n()

/** Primary heart-rate string, or an em dash when the entry carries no value. */
const rhrLabel = computed(() =>
  props.entry.restingHeartRate === null
    ? '—'
    : formatRestingHeartRate(props.entry.restingHeartRate, t),
)

const dateLabel = computed(() => formatHealthEntryDate(props.entry.date, locale.value))
const fromGarmin = computed(() => props.entry.source === 'garmin')
</script>

<template>
  <div class="px-4 py-3">
    <div class="flex items-center justify-between gap-3">
      <p class="text-item-title">{{ rhrLabel }}</p>
      <img
        v-if="fromGarmin"
        :src="INTEGRATION_LOGOS.garminApp"
        :alt="t('health.rhr.sourceGarmin')"
        :title="t('health.rhr.sourceGarmin')"
        class="size-4 shrink-0"
      />
    </div>
    <p class="text-hint">{{ dateLabel }}</p>
  </div>
</template>
