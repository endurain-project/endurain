<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { FastingStats } from '@/features/health/types'

import { Card } from '@/components/ui/card'
import { useUnitFormat } from '@/composables/useUnitFormat'
import { formatHoursMinutes } from '@/features/health/utils/healthFormat'

const props = defineProps<{
  /** Aggregate fasting statistics to summarise. */
  stats: FastingStats
}>()

const { t } = useI18n()
const { duration, percent } = useUnitFormat()

/** The six summary tiles, derived from the raw stats. */
const tiles = computed(() => [
  {
    key: 'totalFasts',
    label: t('health.fasting.stats.totalFasts'),
    value: String(props.stats.totalFasts),
  },
  {
    key: 'currentStreak',
    label: t('health.fasting.stats.currentStreak'),
    value: `${props.stats.currentStreak} ${t('health.fasting.stats.days')}`,
  },
  {
    key: 'longestStreak',
    label: t('health.fasting.stats.longestStreak'),
    value: `${props.stats.longestStreak} ${t('health.fasting.stats.days')}`,
  },
  {
    key: 'avgDuration',
    label: t('health.fasting.stats.avgDuration'),
    value:
      props.stats.avgDurationSeconds != null
        ? formatHoursMinutes(props.stats.avgDurationSeconds, duration)
        : '—',
  },
  {
    key: 'totalTime',
    label: t('health.fasting.stats.totalTime'),
    value: formatHoursMinutes(props.stats.totalFastingSeconds, duration),
  },
  {
    key: 'completionRate',
    label: t('health.fasting.stats.completionRate'),
    value: percent(props.stats.completionRate),
  },
])
</script>

<template>
  <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
    <Card v-for="tile in tiles" :key="tile.key" padding="sm" class="flex flex-col gap-0.5">
      <p class="text-caption">{{ tile.label }}</p>
      <p class="text-metric tabular-nums text-foreground">{{ tile.value }}</p>
    </Card>
  </div>
</template>
